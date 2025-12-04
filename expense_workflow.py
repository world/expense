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
        user_full_name: str = None
    ):
        self.receipt_processor = receipt_processor
        self.browser_agent = browser_agent
        self.logger = logger
        self.test_mode = test_mode
        self.user_full_name = user_full_name
        self.last_used_date: Optional[str] = None
        self.totals_by_currency: Dict[str, float] = {}
        self.receipts_processed = 0
        self.receipts_skipped = 0
    
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
    
    def process_receipt(
        self,
        image_path: Path,
        index: int,
        total: int,
        is_first: bool
    ) -> bool:
        """
        Process a single receipt: OCR, LLM, date resolution, and optionally create in Oracle.
        
        Args:
            image_path: Path to receipt image
            index: Receipt number (1-based)
            total: Total number of receipts
            is_first: Whether this is the first receipt
            
        Returns:
            True if successful
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
            return False
        
        # Step 2: Resolve date
        llm_date = data.get('date')
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
            expense_type=data.get('expense_type', 'Miscellaneous Other'),
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
        
        # Step 5: Create in Oracle (unless test mode)
        if not self.test_mode:
            success = self.browser_agent.create_expense_item(
                expense_type=data.get('expense_type', 'Miscellaneous Other'),
                amount=amount,
                date=final_date,
                merchant=data.get('merchant', 'Unknown'),
                description=data.get('description', 'Expense'),
                receipt_path=str(image_path),
                is_first=is_first,
                user_full_name=self.user_full_name
            )
            
            if success:
                self.logger.info(f"✅ Expense item created in Oracle")
                self.receipts_processed += 1
            else:
                self.logger.error(f"❌ Failed to create expense item in Oracle")
                self.receipts_skipped += 1
                return False
        else:
            self.receipts_processed += 1
        
        return True
    
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
            
            success = self.process_receipt(path, i, total, is_first)
            
            if success and not self.test_mode:
                # Handle "Create Another" vs "Save and Close"
                if not is_last:
                    self.logger.info(f"\n--- Moving to next receipt ({i+1}/{total}) ---")
                    # Try "Create Another" first
                    if not self.browser_agent.click_create_another():
                        # Fall back to regular create item flow
                        self.logger.warning("Create Another failed, will try Create Item for next receipt")
                else:
                    # Last receipt - save and close
                    self.logger.info("\n--- Last receipt, saving and closing ---")
                    self.browser_agent.click_save_and_close()
        
        # Log summary
        self.logger.log_summary(self.totals_by_currency, self.receipts_skipped)
        
        return self.receipts_processed > 0

