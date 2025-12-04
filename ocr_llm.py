"""
OCR and LLM processing for receipts.
"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytesseract
from openai import OpenAI
from PIL import Image, ImageEnhance, ImageFilter


class ReceiptProcessor:
    """Handles OCR extraction and LLM analysis of receipts."""
    
    def __init__(self, llm_client: OpenAI, model: str, expense_types: List[Dict[str, Any]], logger=None):
        self.llm_client = llm_client
        self.model = model
        self.expense_types = expense_types
        self.logger = logger
    
    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Preprocess image for better OCR results.
        
        Args:
            image: PIL Image object
            
        Returns:
            Preprocessed PIL Image
        """
        # Convert to grayscale
        image = image.convert('L')
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2.0)
        
        # Sharpen
        image = image.filter(ImageFilter.SHARPEN)
        
        return image
    
    def extract_text_from_image(self, image_path: Path) -> Tuple[str, List[str]]:
        """
        Extract text from receipt image using OCR.
        
        Args:
            image_path: Path to receipt image
            
        Returns:
            Tuple of (extracted_text, warnings)
        """
        warnings = []
        
        try:
            # Load image
            image = Image.open(image_path)
            
            # Preprocess
            processed = self.preprocess_image(image)
            
            # Run OCR
            text = pytesseract.image_to_string(processed)
            
            if not text or len(text.strip()) < 10:
                warnings.append("OCR extracted very little text - image may be low quality")
            
            if self.logger:
                self.logger.debug(f"OCR extracted {len(text)} characters from {image_path.name}")
            
            return text.strip(), warnings
            
        except Exception as e:
            error_msg = f"OCR failed for {image_path.name}: {str(e)}"
            if self.logger:
                self.logger.error(error_msg)
            warnings.append(error_msg)
            return "", warnings
    
    def build_llm_prompt(self, ocr_text: str) -> List[Dict[str, str]]:
        """
        Build LLM prompt for receipt analysis.
        
        Args:
            ocr_text: Text extracted from receipt via OCR
            
        Returns:
            List of message dicts for OpenAI chat completion
        """
        # Build expense types description
        types_desc = []
        for et in self.expense_types:
            keywords_str = ", ".join(et.get('keywords', []))
            types_desc.append(
                f"- {et['type_key']} (\"{et['type_label']}\"): {keywords_str}"
            )
        types_text = "\n".join(types_desc)
        
        system_prompt = f"""You are an expert at analyzing receipt text and extracting structured expense information.

Available expense types:
{types_text}

Your task:
1. Choose the BEST matching expense type based on the receipt content
2. Extract the merchant/vendor name
3. Extract the total amount (as a number)
4. Identify the currency (default to USD if unclear)
5. Extract the transaction date (in YYYY-MM-DD format)
6. Generate a concise description (max 50 chars)

Return ONLY valid JSON with this exact structure:
{{
  "type_key": "MEAL",
  "type_label": "Meals",
  "merchant": "Chipotle Mexican Grill",
  "total_amount": 42.10,
  "currency": "USD",
  "date": "2025-01-15",
  "description": "Team lunch"
}}

If you cannot find a date, set date to null.
If you cannot determine amount, set it to 0.
Always return valid JSON, nothing else."""

        user_prompt = f"""Analyze this receipt text and extract expense information:

{ocr_text}

Return JSON only."""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    
    def parse_llm_response(self, response_text: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
        """
        Parse LLM JSON response.
        
        Args:
            response_text: Raw LLM response
            
        Returns:
            Tuple of (parsed_data_dict, warnings)
        """
        warnings = []
        
        try:
            # Try to extract JSON if wrapped in markdown code blocks
            if "```json" in response_text:
                match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                if match:
                    response_text = match.group(1)
            elif "```" in response_text:
                match = re.search(r'```\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                if match:
                    response_text = match.group(1)
            
            # Parse JSON
            data = json.loads(response_text.strip())
            
            # Validate required fields
            required = ['type_key', 'type_label', 'merchant', 'total_amount', 'currency']
            for field in required:
                if field not in data:
                    warnings.append(f"LLM response missing field: {field}")
                    return None, warnings
            
            # Validate amount
            try:
                data['total_amount'] = float(data['total_amount'])
                if data['total_amount'] < 0:
                    warnings.append("Amount is negative, using absolute value")
                    data['total_amount'] = abs(data['total_amount'])
            except (ValueError, TypeError):
                warnings.append(f"Invalid amount: {data.get('total_amount')}")
                data['total_amount'] = 0.0
            
            # Validate type against known types
            valid_keys = [et['type_key'] for et in self.expense_types]
            if data['type_key'] not in valid_keys:
                warnings.append(f"Unknown type_key '{data['type_key']}', falling back to OTHER")
                data['type_key'] = 'OTHER'
                data['type_label'] = 'Other'
            
            # Ensure description exists
            if 'description' not in data or not data['description']:
                data['description'] = f"{data['merchant']} - {data['type_label']}"
                warnings.append("Generated description from merchant and type")
            
            # Parse date if present
            date_value = data.get('date')
            if date_value:
                try:
                    # Try to parse as ISO date
                    parsed_date = datetime.fromisoformat(str(date_value))
                    data['date'] = parsed_date.strftime('%d-%m-%Y')
                except (ValueError, TypeError):
                    warnings.append(f"Could not parse date: {date_value}")
                    data['date'] = None
            else:
                data['date'] = None
            
            return data, warnings
            
        except json.JSONDecodeError as e:
            warnings.append(f"LLM response is not valid JSON: {e}")
            if self.logger:
                self.logger.error(f"Invalid JSON from LLM: {response_text[:200]}")
            return None, warnings
        except Exception as e:
            warnings.append(f"Error parsing LLM response: {e}")
            return None, warnings
    
    def analyze_receipt(self, image_path: Path) -> Tuple[Optional[Dict[str, Any]], List[str], str]:
        """
        Full pipeline: OCR + LLM analysis of a receipt.
        
        Args:
            image_path: Path to receipt image
            
        Returns:
            Tuple of (parsed_data, warnings, raw_ocr_text)
        """
        all_warnings = []
        
        # Step 1: OCR
        ocr_text, ocr_warnings = self.extract_text_from_image(image_path)
        all_warnings.extend(ocr_warnings)
        
        if not ocr_text:
            all_warnings.append("No text extracted from image")
            return None, all_warnings, ""
        
        # Step 2: Build LLM prompt
        messages = self.build_llm_prompt(ocr_text)
        
        # Step 3: Call LLM
        try:
            if self.logger:
                self.logger.debug(f"Calling LLM for {image_path.name}...")
            
            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0,
                max_tokens=500
            )
            
            llm_response = response.choices[0].message.content.strip()
            
            if self.logger:
                self.logger.debug(f"LLM response received ({len(llm_response)} chars)")
            
        except Exception as e:
            error_msg = f"LLM call failed: {str(e)}"
            all_warnings.append(error_msg)
            if self.logger:
                self.logger.error(error_msg)
            return None, all_warnings, ocr_text
        
        # Step 4: Parse response
        data, parse_warnings = self.parse_llm_response(llm_response)
        all_warnings.extend(parse_warnings)
        
        if data:
            # Add raw response for verbose logging
            data['_raw_llm_response'] = llm_response
        
        return data, all_warnings, ocr_text

