"""
Receipt processing using LLM vision APIs (Claude/OpenAI) or OCR fallback for other providers.
"""
import base64
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageEnhance, ImageFilter
import pytesseract


class ReceiptProcessor:
    """Handles receipt analysis using vision APIs or OCR fallback."""
    
    def __init__(self, llm_client: Any, model: str, expense_types: List[Dict[str, Any]], provider: str = "openai", logger=None):
        self.llm_client = llm_client
        self.model = model
        self.expense_types = expense_types
        self.provider = provider  # "openai", "anthropic", or "other"
        self.logger = logger
        
        # Determine if we can use vision API
        self.use_vision = provider in ["openai", "anthropic"]
    
    # ========================
    # VISION API METHODS
    # ========================
    
    def encode_image_to_base64(self, image_path: Path) -> Tuple[str, str]:
        """Encode image to base64 for vision API."""
        suffix = image_path.suffix.lower()
        media_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.heic': 'image/heic',
        }
        media_type = media_types.get(suffix, 'image/jpeg')
        
        with open(image_path, 'rb') as f:
            image_data = f.read()
        
        base64_data = base64.standard_b64encode(image_data).decode('utf-8')
        return base64_data, media_type
    
    def build_vision_prompt(self) -> str:
        """Build prompt for vision-based receipt analysis."""
        # expense_types is now just a list of strings
        types_list = "\n".join([f'- "{t}"' for t in self.expense_types])
        
        return f"""Analyze this receipt image and extract expense information.

AVAILABLE EXPENSE TYPES (use exactly as shown):
{types_list}

INSTRUCTIONS:
1. Read the receipt carefully - look for merchant name, date, and total amount
2. Match the merchant to the most appropriate expense type:
   
   HOTELS (Westin, Marriott, Hilton, Hyatt, IHG, etc.):
   - Room charges, lodging, accommodation → "Travel-Hotel Accommodation"
   - Even if breakfast is included, if it's a hotel folio/bill → "Travel-Hotel Accommodation"
   
   MEALS (only for standalone restaurants/cafes):
   - CHECK THE TIME on the receipt if visible!
   - < 11:00 AM → "Meals-Breakfast and Tip"
   - 11:00 AM - 4:00 PM → "Meals-Lunch and Tip"
   - > 4:00 PM → "Meals-Dinner and Tip"
   - If time not visible, guess based on merchant (e.g. "Breakfast Club" → Breakfast)
   - Coffee shops (Starbucks, Dunkin, etc.) → usually "Meals-Breakfast and Tip" unless PM timestamp
   
   TRANSPORTATION:
   - Uber/Lyft/rideshare → "Travel-Non-Car Rental Ground Transport"
   - Gas stations → "Travel-Gasoline"
   - Parking → "Travel-Parking And Tolls"
   - Airlines → "Travel-Airfare"
   - Taxis → "Taxi"
   
   - If unclear → "Miscellaneous Other"

3. Extract the EXACT date shown on receipt in DD-MM-YYYY format
4. Extract the total/final amount (not subtotal)
5. Generate a 2-5 word description of the purchase

REQUIRED OUTPUT - Return ONLY this JSON (no markdown, no explanation):
{{"expense_type":"<exact type from list>","merchant":"<business name>","total_amount":<number>,"currency":"<USD/EUR/etc>","date":"<DD-MM-YYYY>","description":"<2-5 words>","city":"<city name if visible>"}}

If date is not visible, use today: {datetime.now().strftime('%d-%m-%Y')}
If amount unclear, use 0.
If city not visible on receipt, use empty string.

Example:
{{"expense_type":"Meals-Breakfast and Tip","merchant":"Starbucks","total_amount":9.58,"currency":"USD","date":"19-11-2024","description":"Coffee and pastry","city":"Chicago"}}"""
    
    def call_vision_api(self, image_path: Path) -> Tuple[Optional[str], Optional[str]]:
        """Call Claude or OpenAI vision API with receipt image."""
        try:
            base64_data, media_type = self.encode_image_to_base64(image_path)
            prompt = self.build_vision_prompt()
            
            if self.provider == "anthropic":
                response = self.llm_client.messages.create(
                    model=self.model,
                    max_tokens=500,
                    temperature=0,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": base64_data
                                }
                            },
                            {"type": "text", "text": prompt}
                        ]
                    }]
                )
                return response.content[0].text.strip(), None
            else:
                # OpenAI Vision
                response = self.llm_client.chat.completions.create(
                    model=self.model,
                    max_tokens=500,
                    temperature=0,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{media_type};base64,{base64_data}",
                                    "detail": "high"
                                }
                            },
                            {"type": "text", "text": prompt}
                        ]
                    }]
                )
                return response.choices[0].message.content.strip(), None
                
        except Exception as e:
            return None, f"Vision API call failed: {str(e)}"
    
    # ========================
    # OCR FALLBACK METHODS
    # ========================
    
    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """Preprocess image for better OCR results."""
        image = image.convert('L')
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2.0)
        image = image.filter(ImageFilter.SHARPEN)
        return image
    
    def extract_text_ocr(self, image_path: Path) -> Tuple[str, Optional[str]]:
        """Extract text from receipt using Tesseract OCR (fallback for non-vision providers)."""
        try:
            image = Image.open(image_path)
            processed = self.preprocess_image(image)
            text = pytesseract.image_to_string(processed)
            
            if not text or len(text.strip()) < 10:
                return "", "OCR extracted very little text - image may be low quality"
            
            return text.strip(), None
        except Exception as e:
            return "", f"OCR failed: {str(e)}"
    
    def build_ocr_prompt(self, ocr_text: str) -> str:
        """Build prompt for OCR-based text analysis."""
        types_list = "\n".join([f'- "{t}"' for t in self.expense_types])
        
        return f"""Analyze this receipt text and extract expense information.

RECEIPT TEXT:
{ocr_text}

AVAILABLE EXPENSE TYPES:
{types_list}

Return ONLY this JSON (no markdown):
{{"expense_type":"<type from list>","merchant":"<name>","total_amount":<number>,"currency":"USD","date":"<DD-MM-YYYY>","description":"<2-5 words>"}}

If date unclear, use: {datetime.now().strftime('%d-%m-%Y')}"""
    
    def call_text_llm(self, prompt: str) -> Tuple[Optional[str], Optional[str]]:
        """Call LLM with text prompt (for OCR fallback)."""
        try:
            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=500
            )
            return response.choices[0].message.content.strip(), None
        except Exception as e:
            return None, f"LLM call failed: {str(e)}"
    
    # ========================
    # RESPONSE PARSING
    # ========================
    
    def parse_llm_response(self, response_text: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
        """Parse JSON response from LLM."""
        warnings = []
        
        try:
            # Extract JSON from markdown if needed
            if "```json" in response_text:
                match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                if match:
                    response_text = match.group(1)
            elif "```" in response_text:
                match = re.search(r'```\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                if match:
                    response_text = match.group(1)
            
            data = json.loads(response_text.strip())
            
            # Validate required fields (city is optional)
            required = ['expense_type', 'merchant', 'total_amount', 'currency', 'date', 'description']
            # Ensure city field exists even if empty
            if 'city' not in data:
                data['city'] = ''
            missing = [f for f in required if f not in data or data[f] is None or str(data[f]).strip() == '']
            if missing:
                warnings.append(f"Missing required fields: {missing}")
                return None, warnings
            
            # Fix amount
            try:
                data['total_amount'] = abs(float(data['total_amount']))
            except (ValueError, TypeError):
                warnings.append(f"Invalid amount: {data.get('total_amount')}")
                data['total_amount'] = 0.0
            
            # Validate expense_type against known types
            if data['expense_type'] not in self.expense_types:
                # Find closest match or use fallback
                misc_type = next((t for t in self.expense_types if 'Other' in t or 'Misc' in t), None)
                if misc_type:
                    data['expense_type'] = misc_type
                else:
                    data['expense_type'] = self.expense_types[-1]  # Last one is usually "Other"
            
            # Truncate long description
            if data['description'] and len(data['description']) > 100:
                data['description'] = data['description'][:50].strip()
            
            # Validate date
            date_value = data.get('date')
            if date_value:
                parsed_date = None
                for fmt in ['%d-%m-%Y', '%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%m-%d-%Y']:
                    try:
                        parsed_date = datetime.strptime(str(date_value), fmt)
                        break
                    except ValueError:
                        continue
                
                if parsed_date:
                    current_year = datetime.now().year
                    if parsed_date.year < (current_year - 2) or parsed_date.year > (current_year + 1):
                        warnings.append(f"Date year {parsed_date.year} seems incorrect")
                    data['date'] = parsed_date.strftime('%d-%m-%Y')
                else:
                    warnings.append(f"Could not parse date: {date_value}")
                    data['date'] = datetime.now().strftime('%d-%m-%Y')
            else:
                data['date'] = datetime.now().strftime('%d-%m-%Y')
            
            return data, warnings
            
        except json.JSONDecodeError as e:
            warnings.append(f"Invalid JSON: {e}")
            return None, warnings
        except Exception as e:
            warnings.append(f"Parse error: {e}")
            return None, warnings
    
    # ========================
    # MAIN ENTRY POINT
    # ========================
    
    def analyze_receipt(self, image_path: Path) -> Tuple[Optional[Dict[str, Any]], List[str], str, Optional[str]]:
        """
        Analyze receipt - uses Vision API for Claude/OpenAI, OCR fallback for others.
        
        Returns:
            Tuple of (parsed_data, warnings, raw_response, error_reason)
        """
        all_warnings = []
        
        if self.use_vision:
            # Use Vision API (Claude or OpenAI)
            if self.logger:
                self.logger.info(f"📸 Sending image to {self.provider.upper()} Vision API...")
            
            for attempt in range(2):
                response_text, error = self.call_vision_api(image_path)
                
                if error:
                    if attempt == 0:
                        if self.logger:
                            self.logger.warning(f"Vision API failed, retrying... ({error})")
                        continue
                    return None, [error], "", error
                
                data, parse_warnings = self.parse_llm_response(response_text)
                if data:
                    data['_raw_llm_response'] = response_text
                    all_warnings.extend(parse_warnings)
                    return data, all_warnings, response_text, None
                else:
                    if attempt == 0:
                        continue
                    all_warnings.extend(parse_warnings)
                    return None, all_warnings, response_text, parse_warnings[0] if parse_warnings else "Parse failed"
            
            return None, all_warnings, "", "Max attempts exceeded"
        
        else:
            # OCR Fallback for custom/other providers
            if self.logger:
                self.logger.info(f"🔍 Using OCR + text LLM (custom provider)...")
            
            ocr_text, ocr_error = self.extract_text_ocr(image_path)
            if ocr_error:
                all_warnings.append(ocr_error)
            if not ocr_text:
                return None, all_warnings, "", "OCR extracted no text from image"
            
            prompt = self.build_ocr_prompt(ocr_text)
            response_text, error = self.call_text_llm(prompt)
            
            if error:
                return None, [error], ocr_text, error
            
            data, parse_warnings = self.parse_llm_response(response_text)
            if data:
                data['_raw_llm_response'] = response_text
                all_warnings.extend(parse_warnings)
                return data, all_warnings, ocr_text, None
            else:
                all_warnings.extend(parse_warnings)
                return None, all_warnings, ocr_text, parse_warnings[0] if parse_warnings else "Parse failed"
