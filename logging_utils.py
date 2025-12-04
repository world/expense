"""
Centralized logging utilities for the expense helper.
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class ExpenseLogger:
    """Manages structured logging for expense processing."""
    
    def __init__(self, log_file: str = "expense_helper.log", verbose: bool = False):
        self.log_file = Path(log_file)
        self.verbose = verbose
        self.receipt_logs = []
        
        # Configure Python logging
        log_level = logging.DEBUG if verbose else logging.INFO
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_formatter = logging.Formatter(
            '%(levelname)s: %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        
        # File handler
        file_handler = logging.FileHandler(self.log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        
        # Setup root logger
        self.logger = logging.getLogger('expense_helper')
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
    
    def info(self, message: str):
        """Log info message."""
        self.logger.info(message)
    
    def debug(self, message: str):
        """Log debug message."""
        self.logger.debug(message)
    
    def warning(self, message: str):
        """Log warning message."""
        self.logger.warning(message)
    
    def error(self, message: str):
        """Log error message."""
        self.logger.error(message)
    
    def log_receipt(
        self,
        filename: str,
        index: int,
        total_receipts: int,
        type_key: str,
        type_label: str,
        total_amount: float,
        currency: str,
        merchant: str,
        description: str,
        date: str,
        date_source: str,
        warnings: Optional[list] = None,
        status: str = "prepared",
        raw_ocr: Optional[str] = None,
        raw_llm_response: Optional[str] = None
    ):
        """
        Log comprehensive receipt information.
        
        Args:
            filename: Receipt image filename
            index: Receipt number (1-indexed)
            total_receipts: Total number of receipts
            type_key: Internal expense type key
            type_label: Oracle dropdown label
            total_amount: Expense amount
            currency: Currency code
            merchant: Merchant name
            description: Expense description
            date: Final resolved date (DD-MM-YYYY)
            date_source: How date was determined (ocr_llm, fallback_previous, user_prompt)
            warnings: List of warning messages
            status: Processing status (prepared, submitted, failed)
            raw_ocr: Raw OCR text (only logged in verbose mode)
            raw_llm_response: Raw LLM JSON (only logged in verbose mode)
        """
        warnings = warnings or []
        
        # Human-readable summary line
        warning_str = f" [WARNINGS: {len(warnings)}]" if warnings else ""
        summary = (
            f"Receipt #{index}/{total_receipts} '{filename}': "
            f"date={date} (source={date_source}), "
            f"type={type_key}/\"{type_label}\", "
            f"amount={total_amount:.2f} {currency}, "
            f"merchant='{merchant}', "
            f"desc='{description}'{warning_str}"
        )
        self.info(summary)
        
        # Structured JSON log entry
        receipt_data = {
            "timestamp": datetime.now().isoformat(),
            "filename": filename,
            "index": index,
            "total_receipts": total_receipts,
            "type_key": type_key,
            "type_label": type_label,
            "total_amount": total_amount,
            "currency": currency,
            "merchant": merchant,
            "description": description,
            "date": date,
            "date_source": date_source,
            "warnings": warnings,
            "status": status
        }
        
        # Add verbose details if enabled
        if self.verbose:
            if raw_ocr:
                receipt_data["raw_ocr"] = raw_ocr
            if raw_llm_response:
                receipt_data["raw_llm_response"] = raw_llm_response
        
        # Write JSON line to file
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(receipt_data) + '\n')
        
        # Store for summary
        self.receipt_logs.append(receipt_data)
        
        # Log any warnings
        for warning in warnings:
            self.warning(f"  └─ {warning}")
    
    def log_summary(self, totals_by_currency: Dict[str, float], skipped: int = 0):
        """
        Log final summary of all receipts processed.
        
        Args:
            totals_by_currency: Dict mapping currency code to total amount
            skipped: Number of receipts skipped due to errors
        """
        total_processed = len(self.receipt_logs)
        
        # Console summary
        self.info("=" * 70)
        self.info(f"SUMMARY: {total_processed} receipts processed")
        
        if skipped > 0:
            self.warning(f"{skipped} receipts skipped due to errors")
        
        self.info("Total by currency:")
        for currency, total in sorted(totals_by_currency.items()):
            self.info(f"  {currency}: {total:.2f}")
        
        self.info("=" * 70)
        
        # Structured summary to log file
        summary_data = {
            "timestamp": datetime.now().isoformat(),
            "type": "run_summary",
            "total_receipts_processed": total_processed,
            "receipts_skipped": skipped,
            "total_by_currency": totals_by_currency
        }
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(summary_data) + '\n')


