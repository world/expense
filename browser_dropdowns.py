"""
Dropdown selection helpers with validation and retry logic.
"""
import time
from playwright.sync_api import Page


# Global retry constants
MAX_DROPDOWN_RETRIES = 3
DROPDOWN_RETRY_DELAY_MS = 500


def select_expense_type(page: Page, expense_type: str, logger=None) -> bool:
    """
    Select expense type from dropdown with validation and retry.
    
    Args:
        page: Playwright page
        expense_type: Label of expense type to select
        logger: Optional logger
        
    Returns:
        True if successfully selected and verified
    """
    type_selector = "select[id*='ExpenseTypeId'], select[id*='expenseType'], select[id*='ItemType']"
    
    for attempt in range(MAX_DROPDOWN_RETRIES):
        try:
            if logger and attempt > 0:
                logger.info(f"  Retry attempt {attempt + 1}/{MAX_DROPDOWN_RETRIES} for expense type...")
            
            # Wait for selector to be visible
            type_loc = page.locator(type_selector).first
            type_loc.wait_for(state="visible", timeout=2000)
            
            # Click dropdown twice to ensure it opens and options load
            if logger:
                logger.info("  Clicking dropdown to load options...")
            type_loc.click()
            page.wait_for_timeout(100)
            type_loc.click()
            page.wait_for_timeout(100)
            
            # Poll until more than 1 option is visible (first is always blank)
            if logger:
                logger.info("  Waiting for dropdown options to populate...")
            
            options_loaded = False
            for i in range(10):
                try:
                    all_opts = type_loc.locator("option").all()
                    if logger:
                        logger.info(f"    Poll {i+1}/10: Found {len(all_opts)} options")
                    if len(all_opts) > 1:
                        options_loaded = True
                        break
                except Exception:
                    pass
                page.wait_for_timeout(300)
            
            if not options_loaded:
                if logger:
                    logger.warning("  Dropdown options did not load in time")
                if attempt < MAX_DROPDOWN_RETRIES - 1:
                    page.wait_for_timeout(DROPDOWN_RETRY_DELAY_MS)
                    continue
                else:
                    return False
            
            # Select by label
            if logger:
                logger.info(f"  Selecting expense type: {expense_type}")
            type_loc.select_option(label=expense_type, timeout=5000)
            
            # Verify selection
            selected_value = type_loc.evaluate("el => el.value")
            if selected_value and selected_value != "0":
                if logger:
                    logger.info(f"✅ Expense type selected and verified: {expense_type}")
                return True
            else:
                if logger:
                    logger.warning(f"  Selection verification failed (value: {selected_value})")
                if attempt < MAX_DROPDOWN_RETRIES - 1:
                    page.wait_for_timeout(DROPDOWN_RETRY_DELAY_MS)
                    continue
                else:
                    return False
                
        except Exception as e:
            if logger:
                logger.warning(f"  Attempt {attempt + 1} failed: {e}")
            if attempt < MAX_DROPDOWN_RETRIES - 1:
                page.wait_for_timeout(DROPDOWN_RETRY_DELAY_MS)
                continue
            else:
                return False
    
    return False


def select_dropdown_by_value_with_retry(
    page: Page,
    selector: str,
    value: str,
    label: str,
    logger=None
) -> bool:
    """
    Select a dropdown option by value with validation and retry.
    
    Args:
        page: Playwright page
        selector: CSS selector for dropdown
        value: Option value to select
        label: Label for logging (what field this is)
        logger: Optional logger
        
    Returns:
        True if successfully selected and verified
    """
    for attempt in range(MAX_DROPDOWN_RETRIES):
        try:
            if logger and attempt > 0:
                logger.info(f"  Retry attempt {attempt + 1}/{MAX_DROPDOWN_RETRIES} for {label}...")
            
            dropdown = page.locator(selector).first
            dropdown.wait_for(state="visible", timeout=1000)
            
            # Click to open dropdown
            if logger:
                logger.info(f"  Clicking dropdown for {label}...")
            dropdown.click()
            page.wait_for_timeout(200)
            
            # Wait for options to populate
            options_loaded = False
            for i in range(5):
                try:
                    all_opts = dropdown.locator("option").all()
                    if len(all_opts) > 1:
                        options_loaded = True
                        if logger:
                            logger.info(f"    Options loaded for {label} ({len(all_opts)} options)")
                        break
                except Exception:
                    pass
                page.wait_for_timeout(200)
            
            if not options_loaded:
                if logger:
                    logger.warning(f"  Options did not load for {label}")
                if attempt < MAX_DROPDOWN_RETRIES - 1:
                    page.wait_for_timeout(DROPDOWN_RETRY_DELAY_MS)
                    continue
                else:
                    return False
            
            # Select by value
            dropdown.select_option(value=value, timeout=2000)
            
            # Verify selection
            selected = dropdown.evaluate("el => el.value")
            if selected == value:
                if logger:
                    logger.info(f"✅ {label} selected and verified (value: {value})")
                return True
            else:
                if logger:
                    logger.warning(f"  Verification failed for {label} (got {selected}, expected {value})")
                if attempt < MAX_DROPDOWN_RETRIES - 1:
                    page.wait_for_timeout(DROPDOWN_RETRY_DELAY_MS)
                    continue
                else:
                    return False
                
        except Exception as e:
            if logger:
                logger.warning(f"  {label} selection attempt {attempt + 1} failed: {e}")
            if attempt < MAX_DROPDOWN_RETRIES - 1:
                page.wait_for_timeout(DROPDOWN_RETRY_DELAY_MS)
                continue
            else:
                return False
    
    return False
