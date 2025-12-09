"""
Orchestrates the expense item workflow: OCR, LLM, date resolution, and browser automation.
"""
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from browser_agent import OracleBrowserAgent
from ocr_llm import ReceiptProcessor


class ExpenseWorkflow:
    """Manages the end-to-end expense report creation workflow."""
    
    def __init__(
        self,
        receipt_processor: ReceiptProcessor,
        browser_agent: OracleBrowserAgent,
        logger,
        test_mode: bool = False,
        user_full_name: str = None,
        travel_agency: str = "AMEX GBT"
    ):
        self.receipt_processor = receipt_processor
        self.browser_agent = browser_agent
        self.logger = logger
        self.test_mode = test_mode
        self.user_full_name = user_full_name
        self.travel_agency = travel_agency
        self.last_used_date: Optional[str] = None
        self.totals_by_currency: Dict[str, float] = {}
        self.receipts_processed = 0
        self.receipts_skipped = 0
        self.receipts_duplicate = 0  # Track duplicates separately
        self.existing_items: List[Dict] = []  # Track items already in the report
    
    def resolve_date(self, llm_date: Optional[str], receipt_index: int, receipt_filename: str) -> Tuple[str, str]:
        """
        Resolve the date for a receipt using the 3-step algorithm.
        
        Args:
            llm_date: Date extracted by LLM (DD-MM-YYYY or None)
            receipt_index: Index of current receipt (1-based)
            receipt_filename: Name of receipt file
            
        Returns:
            Tuple of (resolved_date, date_source)
        """
        # Step 1: Try LLM/OCR date
        if llm_date and self.validate_date_format(llm_date):
            self.last_used_date = llm_date
            return llm_date, "ocr_llm"
        
        # Step 2: Try last used date
        if self.last_used_date:
            self.logger.warning(f"Could not extract date from receipt, using last date: {self.last_used_date}")
            return self.last_used_date, "fallback_previous"
        
        # Step 3: Prompt user
        self.logger.warning(f"No date found for first receipt '{receipt_filename}'")
        date = self.prompt_user_for_date()
        self.last_used_date = date
        return date, "user_prompt"
    
    def validate_date_format(self, date_str: str) -> bool:
        """
        Validate date is in DD-MM-YYYY format.
        
        Args:
            date_str: Date string to validate
            
        Returns:
            True if valid
        """
        try:
            datetime.strptime(date_str, '%d-%m-%Y')
            return True
        except ValueError:
            return False
    
    def prompt_user_for_date(self) -> str:
        """
        Prompt user to enter a date.
        
        Returns:
            Validated date string in DD-MM-YYYY format
        """
        print("\n" + "=" * 70)
        print("📅 DATE REQUIRED")
        print("=" * 70)
        print("Please enter the expense date for this receipt.")
        print("Format: DD-MM-YYYY (e.g., 15-01-2025)")
        print("=" * 70)
        
        while True:
            date_str = input("Enter date: ").strip()
            if self.validate_date_format(date_str):
                return date_str
            else:
                print("❌ Invalid date format. Please use DD-MM-YYYY (e.g., 15-01-2025)")
    
    def is_duplicate(self, amount: float, merchant: str, date: str = "") -> bool:
        """
        Check if an expense item already exists in the report.
        
        Args:
            amount: Expense amount
            merchant: Merchant name
            date: Expense date (DD-MM-YYYY format, optional)
            
        Returns:
            True if duplicate found
        """
        for existing in self.existing_items:
            # Match on exact amount (within 1 cent)
            if abs(existing['amount'] - amount) < 0.01:
                # If merchant is also available and matches, it's definitely a duplicate
                existing_merchant = existing.get('merchant', '').lower().strip()
                new_merchant = merchant.lower().strip()
                
                # Match if merchants are similar (one contains the other)
                if existing_merchant and new_merchant:
                    if existing_merchant in new_merchant or new_merchant in existing_merchant:
                        # If we also have dates, verify they match (convert formats if needed)
                        existing_date = existing.get('date', '')
                        if existing_date and date:
                            # Convert DD-MM-YYYY to DD-MMM-YYYY for comparison
                            # existing_date is like "19-Nov-2025", date is like "19-11-2025"
                            try:
                                from datetime import datetime
                                parsed_new = datetime.strptime(date, '%d-%m-%Y')
                                formatted_new = parsed_new.strftime('%d-%b-%Y')
                                if formatted_new.lower() == existing_date.lower():
                                    return True
                            except:
                                # If date parsing fails, just match on amount+merchant
                                return True
                        else:
                            # No dates to compare, match on amount+merchant
                            return True
                else:
                    # If no merchant info, just match on amount
                    return True
        
        return False
    
    def process_receipt(
        self,
        image_path: Path,
        index: int,
        total: int,
        is_first: bool
    ) -> tuple[bool, bool]:
        """
        Process a single receipt: OCR, LLM, date resolution, and optionally create in Oracle.
        
        Args:
            image_path: Path to receipt image
            index: Receipt number (1-based)
            total: Total number of receipts
            is_first: Whether this is the first receipt
            
        Returns:
            (success, created_in_oracle): success=True if no errors, created_in_oracle=True if item was added to Oracle
        """
        self.logger.info(f"\n{'='*70}")
        self.logger.info(f"Processing receipt #{index}/{total}: {image_path.name}")
        self.logger.info(f"{'='*70}")
        
        # Step 1: OCR + LLM analysis
        data, warnings, raw_ocr, error_reason = self.receipt_processor.analyze_receipt(image_path)
        
        if not data:
            # Show the actual error reason
            if error_reason:
                self.logger.error(f"Failed to analyze receipt {image_path.name}")
                self.logger.error(f"  REASON: {error_reason}")
            else:
                self.logger.error(f"Failed to analyze receipt {image_path.name}")
            
            # Also show any additional warnings
            if warnings:
                for warning in warnings:
                    self.logger.warning(f"  └─ {warning}")
            
            self.receipts_skipped += 1
            return (False, False)
        
        # Step 2: Resolve date
        # For hotels, prefer the check-in date so top-level Date matches first night of stay
        expense_type_label = data.get('expense_type', 'Miscellaneous Other')
        llm_date = data.get('date')
        if 'hotel' in expense_type_label.lower():
            check_in = data.get('check_in_date')
            if check_in:
                llm_date = check_in
        final_date, date_source = self.resolve_date(llm_date, index, image_path.name)
        
        # Step 3: Accumulate totals
        currency = data.get('currency', 'USD')
        amount = data.get('total_amount', 0.0)
        if currency not in self.totals_by_currency:
            self.totals_by_currency[currency] = 0.0
        self.totals_by_currency[currency] += amount
        
        # Step 4: Log receipt
        status = "prepared" if self.test_mode else "pending"
        
        self.logger.log_receipt(
            filename=image_path.name,
            index=index,
            total_receipts=total,
            expense_type=expense_type_label,
            total_amount=amount,
            currency=currency,
            merchant=data.get('merchant', 'Unknown'),
            description=data.get('description', 'Expense'),
            date=final_date,
            date_source=date_source,
            warnings=warnings,
            status=status,
            raw_ocr=raw_ocr if self.logger.verbose else None,
            raw_llm_response=data.get('_raw_llm_response') if self.logger.verbose else None
        )
        
        # Step 5: Check for duplicates, then create in Oracle (unless test mode)
        if not self.test_mode:
            # Check if this item already exists
            merchant = data.get('merchant', 'Unknown')
            if self.is_duplicate(amount, merchant, final_date):
                self.logger.info(f"⏭️  Already filed: {final_date} | ${amount:.2f} | {merchant}")
                self.receipts_duplicate += 1
                return (True, False)  # Success but not created in Oracle (duplicate)
            
            success = self.browser_agent.create_expense_item(
                expense_type=data.get('expense_type', 'Miscellaneous Other'),
                amount=amount,
                date=final_date,
                merchant=merchant,
                description=data.get('description', 'Expense'),
                receipt_path=str(image_path),
                is_first=is_first,
                ticket_number=data.get('ticket_number', ''),
                departure_city=data.get('departure_city', ''),
                arrival_city=data.get('arrival_city', ''),
                flight_type=data.get('flight_type', ''),
                flight_class=data.get('flight_class', ''),
                nights=int(data.get('nights', 0) or 0),
                check_in_date=data.get('check_in_date', ''),
                check_out_date=data.get('check_out_date', '')
            )
            
            if success:
                self.logger.info(f"✅ Expense item fully created in Oracle (all fields filled)")
                self.receipts_processed += 1
                # Add to existing items to prevent future duplicates
                self.existing_items.append({
                    'amount': amount,
                    'merchant': merchant,
                    'date': final_date
                })
                return (True, True)  # Success and created in Oracle
            else:
                self.logger.error(f"❌ Failed to create expense item in Oracle")
                self.receipts_skipped += 1
                return (False, False)
        else:
            # Test mode - no Oracle interaction
            self.receipts_processed += 1
            return (True, False)
    
    def process_all_receipts(self, receipt_paths: List[Path]) -> bool:
        """
        Process all receipts in sequence.
        
        Args:
            receipt_paths: List of paths to receipt images
            
        Returns:
            True if at least some receipts were processed
        """
        total = len(receipt_paths)
        
        if total == 0:
            self.logger.warning("No receipts to process")
            return False
        
        self.logger.info(f"\n🚀 Starting processing of {total} receipt(s)...")
        
        for i, path in enumerate(receipt_paths, start=1):
            is_first = (i == 1)
            is_last = (i == total)
            
            success, created_in_oracle = self.process_receipt(path, i, total, is_first)
            
            # Only click buttons if we actually created an item in Oracle
            if created_in_oracle:
                # Handle "Create Another" vs "Save and Close"
                if not is_last:
                    self.logger.info(f"\n--- Moving to next receipt ({i+1}/{total}) ---")
                    # Try "Create Another" first
                    if not self.browser_agent.click_create_another():
                        # Fall back to regular create item flow
                        self.logger.warning("Create Another failed, will try Create Item for next receipt")
                else:
                    # Last receipt - save and close, then STOP doing any further browser interactions
                    import time
                    self.logger.info(f"\n⏱️  [TIMESTAMP] About to call click_save_and_close at {time.time():.3f}")
                    self.logger.info("\n--- Last receipt, saving and closing ---")
                    self.browser_agent.click_save_and_close()
                    self.logger.info(f"⏱️  [TIMESTAMP] click_save_and_close returned at {time.time():.3f}")

                    # Immediately break out after Save and Close to avoid any stray interactions
                    break
        
        # Log summary (pure logging, no browser interaction)
        self.logger.log_summary(self.totals_by_currency, self.receipts_skipped, self.receipts_duplicate)
        
        return (self.receipts_processed + self.receipts_duplicate) > 0

