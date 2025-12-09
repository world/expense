"""
Common field filling functions for Oracle expense forms.
"""
from datetime import datetime
from pathlib import Path
import time
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from debug_utils import maybe_dump_page_html


def fill_date_field(page: Page, date: str, logger=None) -> bool:
    """
    Fill the Date field with DD-MMM-YYYY format.
    
    Args:
        page: Playwright page
        date: Date in DD-MM-YYYY format
        logger: Optional logger
        
    Returns:
        True if successfully filled
    """
    if logger:
        logger.info(f"📅 Filling date: {date}")
    
    # Convert date from DD-MM-YYYY to DD-MMM-YYYY format for Oracle
    oracle_date = date
    try:
        # Try parsing DD-MM-YYYY format
        if '-' in date and len(date.split('-')[1]) <= 2:
            parsed = datetime.strptime(date, "%d-%m-%Y")
            oracle_date = parsed.strftime("%d-%b-%Y")  # e.g., "19-Nov-2025"
            if logger:
                logger.info(f"📅 Converted to Oracle format: {oracle_date}")
    except:
        pass  # Keep original if conversion fails
    
    date_selector = "input[id*='StartDate'], input[placeholder*='dd-mmm'], input[aria-label='Date']"
    
    try:
        loc = page.locator(date_selector).first
        loc.wait_for(state="visible", timeout=2000)
        loc.fill(oracle_date)
        if logger:
            logger.info(f"✅ Filled date: {oracle_date}")
        return True
    except Exception as e:
        if logger:
            logger.warning(f"Could not fill Date field: {e}")
        return False


def fill_amount_field(page: Page, amount: float, logger=None) -> bool:
    """
    Fill the Amount field.
    
    Args:
        page: Playwright page
        amount: Amount value
        logger: Optional logger
        
    Returns:
        True if successfully filled
    """
    if logger:
        logger.info(f"💵 Filling amount: {amount}")
    
    amount_selector = "input[id*='ReceiptAmount'], input[id*='amount' i], input[name*='amount' i]"
    try:
        amount_loc = page.locator(amount_selector).first
        amount_loc.wait_for(state="visible", timeout=500)
        amount_loc.fill(str(amount))
        if logger:
            logger.info(f"✅ Filled amount: {amount}")
        return True
    except Exception as e:
        if logger:
            logger.warning(f"Could not fill Amount field: {e}")
        return False


def fill_description_field(page: Page, description: str, logger=None) -> bool:
    """
    Fill the Description field.
    
    Args:
        page: Playwright page
        description: Description text
        logger: Optional logger
        
    Returns:
        True if successfully filled
    """
    if not description:
        return True
        
    if logger:
        logger.info(f"📝 Filling description: {description}")
    
    desc_selector = "input[id*='Description'], input[id*='description' i], textarea[id*='Description'], input[aria-label*='Description'], input[id*='Justification'], textarea[id*='Justification']"
    try:
        desc_loc = page.locator(desc_selector).first
        # Rely on Playwright's built-in waiting instead of our own short timeout
        desc_loc.fill(description)
        if logger:
            logger.info(f"✅ Filled description: {description}")
        return True
    except Exception as e:
        if logger:
            logger.warning(f"Could not fill Description field: {e}")
        return False


def fill_merchant_field(page: Page, merchant: str, logger=None) -> bool:
    """
    Fill the Merchant name field.
    
    Args:
        page: Playwright page
        merchant: Merchant name
        logger: Optional logger
        
    Returns:
        True if successfully filled
    """
    if not merchant:
        return True
        
    if logger:
        logger.info(f"🏪 Filling merchant: {merchant}")
    
    merchant_selector = "input[id*='Merchant'], input[id*='merchant' i], input[name*='merchant' i], input[aria-label*='Merchant']"
    try:
        merchant_loc = page.locator(merchant_selector).first
        # Rely on Playwright's default actionability/timeout here as well
        merchant_loc.fill(merchant)
        if logger:
            logger.info(f"✅ Filled merchant: {merchant}")
        return True
    except Exception as e:
        if logger:
            logger.warning(f"Could not fill Merchant field: {e}")
        return False


def upload_receipt_attachment(page: Page, receipt_path: str, logger=None) -> bool:
    """
    Upload a receipt image via Oracle's attachment dropzone.
    
    Args:
        page: Playwright page
        receipt_path: Path to receipt image
        logger: Optional logger
        
    Returns:
        True if successfully uploaded
    """
    if not receipt_path:
        return True
    
    if logger:
        logger.info("⏳ Waiting for attachments dropzone (appears after type)...")
    
    # Oracle dropzone has id containing pglDropZone or cilDzMsg
    dropzone_selectors = [
        "[id*='pglDropZone']",
        "[id*='cilDzMsg']",
        "div.FndDropzone",
        "a[title='Add File']"
    ]
    
    attachment_appeared = False
    for sel in dropzone_selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=500)
            attachment_appeared = True
            if logger:
                logger.info(f"✅ Attachments dropzone appeared (found via {sel})")
            break
        except:
            continue
    
    if not attachment_appeared:
        if logger:
            logger.info("⏳ Attachments dropzone not visible yet")
        return False
    
    # Optional full-page HTML snapshot before we touch the file input, so we
    # can analyze the attachment markup when debugging (-d / --dump-html).
    maybe_dump_page_html(page, logger, name="before_attachment_upload")
    
    # Upload receipt using Oracle's own dropzone flow:
    # 1. Click the "Add File" control to trigger the ADF dropzone logic.
    # 2. Use Playwright's file chooser to set the file(s).
    # 3. Wait for the attachment list widget to show at least one row.
    if logger:
        logger.info("📎 Uploading receipt attachment...")

    try:
        # Step 1: trigger the ADF dropzone "Add File" action which wires up
        # the hidden input and progress panel correctly.
        add_file_anchor = page.locator(
            "a[id*='dciAvsd:sfAvsd:dzAvsd:cilDzMsg'][title='Add File']"
        ).first

        # Use Playwright's recommended pattern for file uploads.
        try:
            with page.expect_file_chooser(timeout=5000) as fc_info:
                add_file_anchor.click()
            file_chooser = fc_info.value
            file_chooser.set_files(receipt_path)
            if logger:
                logger.info("  ✅ File chooser used to attach receipt")
        except PlaywrightTimeoutError:
            # Fallback: directly set the hidden dzHfile input associated with
            # this dropzone, in case the environment suppresses file choosers.
            hidden_input = page.locator(
                "span.FndDropzoneInputFilePanelHide input[type='file'][id$='pglAdfIf::dzHfile']"
            ).first
            hidden_input.set_input_files(receipt_path)
            if logger:
                logger.info("  ⚠️ File chooser not triggered, set files directly on hidden dzHfile input")

        if logger:
            logger.info("⏳ Waiting for attachment row to appear...")

        # Step 3: wait for the attachment list to show at least one row that
        # is not the "No attachments to display" placeholder.
        list_container = page.locator(
            "div[title='Attachment List'], div[id*=':lvAvsd']"
        ).first

        upload_success = False
        max_wait = 60.0
        start = time.monotonic()

        while True:
            elapsed = time.monotonic() - start
            if elapsed >= max_wait:
                break

            try:
                if list_container.is_visible(timeout=2000):
                    text = (list_container.inner_text() or "").strip()
                    if text and "No attachments to display" not in text:
                        upload_success = True
                        break
            except Exception:
                # List may not be present/visible yet; keep polling
                pass

            if logger:
                bars = int((elapsed / max_wait) * 20)
                progress = f"[{'█' * bars}{'░' * (20 - bars)}] {elapsed:.1f}s / {max_wait:.0f}s"
                logger.info(f"  📤 Uploading... {progress}")

            page.wait_for_timeout(1000)

        if not upload_success and logger:
            logger.warning("⚠️  Attachment list did not show a file row before timeout")

        return True

    except Exception as e:
        if logger:
            logger.warning(f"⚠️  Attachment upload failed: {e}")
        return False

