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
from anthropic import Anthropic
from PIL import Image, ImageEnhance, ImageFilter


class ReceiptProcessor:
    """Handles OCR extraction and LLM analysis of receipts."""
    
    def __init__(self, llm_client: Any, model: str, expense_types: List[Dict[str, Any]], provider: str = "openai", logger=None):
        self.llm_client = llm_client
        self.model = model
        self.expense_types = expense_types
        self.provider = provider  # "openai" or "anthropic"
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
        # Build clean list of expense types
        types_list = []
        for et in self.expense_types:
            types_list.append(f"  - {et['type_key']}: \"{et['type_label']}\"")
        types_text = "\n".join(types_list)
        
        system_prompt = f"""You are an expert at analyzing receipt text and extracting structured expense information.

Available expense types:
{types_text}

Your task:
1. FIRST, identify the merchant/vendor name from the receipt
2. INFER the most appropriate expense type based on what kind of business the merchant is:
   - Coffee shops (Starbucks, Dunkin) → Meals-Breakfast and Tip
   - Lunch places (Chipotle, Subway) → Meals-Lunch and Tip
   - Restaurants (dinner) → Meals-Dinner and Tip
   - Airlines → Travel-Airfare
   - Hotels → Travel-Hotel Accommodation
   - Uber/Lyft → Travel-Non-Car Rental Ground Transport
   - Gas stations → Travel-Gasoline
   - Parking → Travel-Parking And Tolls
   - Taxis → Taxi
   - Office stores → Office And Print Supplies
   - Software/subscriptions → Software
   - Phone carriers → Mobile Phone
   - Shipping services → Shipping
   - Training/courses → Training
   - If unclear → Miscellaneous Other
3. Extract the total amount (as a number)
4. Identify the currency (default to USD if unclear)
5. Extract the transaction date in DD-MM-YYYY format (e.g., 15-01-2025 for January 15, 2025)
6. Generate a concise description (max 50 chars)

CRITICAL INSTRUCTIONS - YOU MUST FOLLOW EXACTLY:
1. Return ONLY a single JSON object - no markdown, no explanations
2. Include ALL 7 required fields: type_key, type_label, merchant, total_amount, currency, date, description
3. Date: Extract from receipt in DD-MM-YYYY format (e.g., "15-01-2025"). If no date visible, use today's date: {datetime.now().strftime('%d-%m-%Y')}
4. Description: Concise 2-5 word description based on merchant (e.g., "Coffee and snack", "Rideshare to airport", "Hotel stay")
5. type_key must match one of: {', '.join([et['type_key'] for et in self.expense_types])}

Example format (you must follow this exact structure):
{{"type_key":"MEALS_BREAKFAST","type_label":"Meals-Breakfast and Tip","merchant":"Starbucks","total_amount":15.75,"currency":"USD","date":"15-01-2025","description":"Coffee and snack"}}

ALL 7 fields are REQUIRED and MUST have values (no null, no empty strings)."""

        user_prompt = f"""Receipt text:
{ocr_text}

Return ONLY the JSON with all 7 fields. Remember: date must be DD-MM-YYYY (use {datetime.now().strftime('%d-%m-%Y')} if unclear), description must be concise (2-5 words)."""

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
            
            # Validate all 7 required fields
            required = ['type_key', 'type_label', 'merchant', 'total_amount', 'currency', 'date', 'description']
            missing = [field for field in required if field not in data or data[field] is None or str(data[field]).strip() == '']
            if missing:
                warnings.append(f"LLM response missing required fields: {missing}")
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
            
            # Validate description is concise
            if data['description'] and len(data['description']) > 100:
                warnings.append(f"Description too long ({len(data['description'])} chars), truncating to 50 chars")
                data['description'] = data['description'][:50].strip()
            
            # Parse and normalize date
            date_value = data.get('date')
            if date_value and str(date_value).lower() not in ['null', 'none', '']:
                try:
                    # Remove any None or 'null' string values
                    if str(date_value).lower() in ['null', 'none']:
                        data['date'] = None
                    else:
                        # Try multiple date formats
                        date_str = str(date_value)
                        parsed_date = None
                        
                        # Try DD-MM-YYYY (target format)
                        for fmt in ['%d-%m-%Y', '%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
                            try:
                                parsed_date = datetime.strptime(date_str, fmt)
                                break
                            except ValueError:
                                continue
                        
                        if parsed_date:
                            # Always convert to DD-MM-YYYY format
                            data['date'] = parsed_date.strftime('%d-%m-%Y')
                        else:
                            warnings.append(f"Could not parse date: {date_value}")
                            data['date'] = None
                except (ValueError, TypeError) as e:
                    warnings.append(f"Date parsing error: {e}")
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
    
    def call_llm_with_retry(self, messages: List[Dict[str, str]], max_retries: int = 3) -> Tuple[Optional[str], Optional[str]]:
        """
        Call LLM with retry logic for malformed responses.
        
        Returns:
            Tuple of (llm_response, error_message)
        """
        for attempt in range(max_retries):
            try:
                if self.provider == "anthropic":
                    response = self.llm_client.messages.create(
                        model=self.model,
                        max_tokens=500,
                        temperature=0,
                        messages=[{"role": "user", "content": messages[1]["content"]}]
                    )
                    llm_response = response.content[0].text.strip()
                else:
                    response = self.llm_client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=0,
                        max_tokens=500
                    )
                    llm_response = response.choices[0].message.content.strip()
                
                return llm_response, None
                
            except Exception as e:
                if attempt < max_retries - 1:
                    if self.logger:
                        self.logger.warning(f"LLM call attempt {attempt + 1} failed, retrying...")
                    continue
                else:
                    return None, f"LLM API call failed after {max_retries} attempts: {str(e)}"
        
        return None, "Max retries exceeded"
    
    def analyze_receipt(self, image_path: Path) -> Tuple[Optional[Dict[str, Any]], List[str], str, Optional[str]]:
        """
        Full pipeline: OCR + LLM analysis of a receipt.
        
        Args:
            image_path: Path to receipt image
            
        Returns:
            Tuple of (parsed_data, warnings, raw_ocr_text, error_reason)
        """
        all_warnings = []
        error_reason = None
        
        # Step 1: OCR
        ocr_text, ocr_warnings = self.extract_text_from_image(image_path)
        all_warnings.extend(ocr_warnings)
        
        if not ocr_text:
            error_reason = "No text extracted from image via OCR"
            all_warnings.append(error_reason)
            return None, all_warnings, "", error_reason
        
        # Step 2: Build LLM prompt
        messages = self.build_llm_prompt(ocr_text)
        
        # Step 3: Call LLM with retry for missing fields
        max_attempts = 3
        for attempt in range(max_attempts):
            if self.logger:
                self.logger.debug(f"Calling LLM for {image_path.name}... (attempt {attempt + 1}/{max_attempts})")
            
            llm_response, error = self.call_llm_with_retry(messages)
            
            if error:
                error_reason = error
                all_warnings.append(error_reason)
                if self.logger:
                    self.logger.error(error_reason)
                return None, all_warnings, ocr_text, error_reason
            
            if self.logger:
                self.logger.debug(f"LLM response received ({len(llm_response)} chars)")
            
            # Step 4: Parse response
            data, parse_warnings = self.parse_llm_response(llm_response)
            
            if data:
                # Success! All required fields present
                data['_raw_llm_response'] = llm_response
                return data, all_warnings, ocr_text, None
            else:
                # Check if it's a missing required field issue
                if attempt < max_attempts - 1:
                    # Retry with more explicit prompt
                    if self.logger:
                        self.logger.warning(f"⚠️  LLM response had issues. Retrying with more explicit instructions...")
                        self.logger.debug(f"   Parse warnings: {parse_warnings}")
                        self.logger.debug(f"   LLM response was: {llm_response[:300]}")
                    
                    # Add feedback about what was wrong
                    feedback = "\n\nYour previous response had issues:\n"
                    feedback += "\n".join(f"- {w}" for w in parse_warnings)
                    feedback += "\n\nPlease return a VALID JSON object with ALL 7 required fields: type_key, type_label, merchant, total_amount, currency, date, description"
                    messages[1]["content"] += feedback
                    continue
                else:
                    # Final attempt failed
                    all_warnings.extend(parse_warnings)
                    error_reason = f"LLM failed after {attempt + 1} attempts. Last error: {parse_warnings[0] if parse_warnings else 'Unknown'}"
                    if self.logger:
                        self.logger.error(f"   Final LLM response was: {llm_response}")
                    return None, all_warnings, ocr_text, error_reason
        
        return None, all_warnings, ocr_text, "Max parsing attempts exceeded"


