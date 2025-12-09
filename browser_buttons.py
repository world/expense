"""
Button click handlers for Oracle expense forms (Create Item, Create Another, Save and Close).
"""
import time
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from debug_utils import maybe_dump_page_html
def click_create_item(page: Page, logger=None) -> bool:
    """
    Click 'Create Item' button to start a new expense item.
    
    Args:
        page: Playwright page
        logger: Optional logger
        
    Returns:
        True if successfully clicked
    """
    if logger:
        logger.info("Clicking 'Create Item'...")
    
    # Use the most reliable selector directly
    try:
        page.locator("span.xrk:has-text('Create Item')").first.click(timeout=500)
        if logger:
            logger.info("✅ Clicked Create Item")
    except Exception as e:
        if logger:
            logger.warning(f"First selector failed, trying fallback...")
        # Fallback
        try:
            page.locator("text=Create Item").first.click(timeout=500)
            if logger:
                logger.info("✅ Clicked Create Item (fallback)")
        except:
            if logger:
                logger.error("Could not find Create Item button")
            return False
    
    # Smart wait: wait for form to load (date field visible)
    page.wait_for_load_state("domcontentloaded")
    return True


def click_create_another(page: Page, logger=None) -> bool:
    """
    Click 'Create Another' button to add another expense item.
    Uses Tab + Space/Enter keyboard method for Oracle ADF reliability.
    
    Args:
        page: Playwright page
        logger: Optional logger
        
    Returns:
        True if button found and clicked
    """
    if logger:
        logger.info("➕ Clicking 'Create Another'...")
    
    clicked = False
    
    # Strategy: Tab from label to find the button
    try:
        # Focus the label
        label = page.locator("text=Create Expense Item").first
        if label.is_visible():
            if logger:
                logger.info("  Focusing 'Create Expense Item' label...")
            label.click()  # Click to ensure focus context
            
            # Tab and log focus 15 times
            for i in range(15):
                page.keyboard.press("Tab")
                page.wait_for_timeout(100)
                
                # Get focused element details
                focused_text = page.evaluate("document.activeElement.innerText")
                focused_tag = page.evaluate("document.activeElement.tagName")
                
                if logger:
                    short_text = (focused_text[:40] + '..') if focused_text and len(focused_text) > 40 else focused_text
                    logger.info(f"  Tab #{i+1}: <{focused_tag}> '{short_text}'")
                
                # Check if we found it
                if focused_text and "Create Another" in focused_text:
                    if logger:
                        logger.info("  🎯 FOUND IT! Pressing Space...")
                    
                    # Settle time
                    page.wait_for_timeout(500)
                    
                    # Try Space (Primary method) - Hold for 200ms
                    page.keyboard.down("Space")
                    page.wait_for_timeout(200)
                    page.keyboard.up("Space")
                    
                    # Quick check for success after 1s
                    page.wait_for_timeout(1000)
                    
                    try:
                        date_val = page.locator("input[id*='StartDate']").first.input_value()
                        if not date_val:
                            if logger:
                                logger.info("  ✅ Success! Form reset detected immediately.")
                            clicked = True
                            break
                    except:
                        pass
                        
                    # If Space failed, try Enter immediately
                    if logger:
                        logger.info("  ⚠️ Space didn't trigger yet, trying Enter...")
                    page.keyboard.press("Enter")
                    
                    clicked = True
                    break
    except Exception as e:
        if logger:
            logger.warning(f"  Tab trace failed: {e}")
    
    if not clicked:
        if logger:
            logger.warning("Could not find/click 'Create Another' button")
        return False
    
    return True


def click_save_and_close(page: Page, logger=None) -> bool:
    """
    Click the primary 'Save and Close' button itself (not the dropdown arrow).
    
    Args:
        page: Playwright page
        logger: Optional logger
        
    Returns:
        True if successfully clicked
    """
    # Optional debug snapshot before attempting Save and Close
    maybe_dump_page_html(page, logger, name="before_save_and_close")

    # Before saving, move focus back to the top-level Amount field.
    # This helps Oracle finish any partial-page updates in the itemization area.
    try:
        amount_loc = page.locator(
            "input[id*='ReceiptAmount'], input[id*='amount' i], input[name*='amount' i]"
        ).first
        if amount_loc:
            if logger:
                logger.info("🎯 Focusing top-level Amount field before Save and Close...")
            amount_loc.click(timeout=1000)
            # Small pause to let Oracle commit any pending changes
            page.wait_for_timeout(200)
    except Exception as e:
        if logger:
            logger.warning(f"Could not focus top-level Amount field before Save and Close: {e}")

    # Give Oracle a full second to process any just-filled fields before attempting to save
    if logger:
        logger.info("⏸️  Pausing 1s before Save and Close to let Oracle process all fields...")
    page.wait_for_timeout(1000)
    
    if logger:
        logger.info("💾 Now clicking main 'Save and Close' button...")

    try:
        # We have strong empirical evidence that Oracle ADF only fires the
        # correct handler when the user *tabs* to the button and then presses
        # Space/Enter. Direct clicks and synthetic key events on the anchor
        # itself are ignored due to onclick="this.focus();return false".
        #
        # To mimic this without the old 15-tab global hack, we:
        # 1. Move focus into the small toolbar region that contains
        #    "Create Another" and "Save and Close".
        # 2. Send a tiny number of Tabs locally until the activeElement
        #    is the Save and Close button.
        # 3. Then send a real Space key via Playwright.

        # Step 1: Click / focus somewhere in the toolbar row
        # Prefer the Create Another button if present (stable neighbor).
        toolbar_focused = False
        try:
            create_another = page.locator(
                "a.xrg[role='button']:has(span.xrk:has-text('Create Another'))"
            ).first
            if create_another.is_visible():
                create_another.click(timeout=1000)
                toolbar_focused = True
                if logger:
                    logger.info("  🎯 Seed focus on 'Create Another' before tabbing to Save and Close")
        except Exception:
            pass

        # Fallback: click near the Save and Close container itself
        if not toolbar_focused:
            try:
                save_container = page.locator(
                    "div[id$='SaveAndCloseButton'].xeq.p_AFTextOnly"
                ).first
                save_container.click(timeout=1000)
                toolbar_focused = True
                if logger:
                    logger.info("  🎯 Seed focus on Save and Close container before tabbing")
            except Exception as e:
                if logger:
                    logger.error(f"  ❌ Could not seed focus in Save/Create toolbar: {e}")
                return False

        # Small pause to let Oracle update internal focus state
        page.wait_for_timeout(150)

        # Step 2: Local tabbing to land exactly on Save and Close
        found = False
        for i in range(6):  # local, bounded – NOT the old 15-tab global walk
            page.keyboard.press("Tab")
            page.wait_for_timeout(120)

            active_info = page.evaluate(
                """
                () => {
                    const el = document.activeElement;
                    if (!el) return { tag: null, text: null, title: null, id: null, role: null, classes: null };
                    return {
                        tag: el.tagName,
                        text: (el.innerText || '').trim(),
                        title: el.getAttribute('title'),
                        id: el.id || null,
                        role: el.getAttribute('role'),
                        classes: el.className || null
                    };
                }
                """
            )

            if logger:
                short_text = (active_info["text"][:40] + "..") if active_info["text"] and len(active_info["text"]) > 40 else active_info["text"]
                logger.info(
                    f"  Tab to SaveAndClose #{i+1}: <{active_info['tag']}> "
                    f"id='{active_info['id']}' role='{active_info['role']}' "
                    f"text='{short_text}'"
                )

            text = (active_info["text"] or "") + " " + (active_info["title"] or "")
            if (
                "Save and Close" in text
                and active_info["tag"] == "A"
                and (active_info["role"] == "button")
            ):
                found = True
                if logger:
                    logger.info("  🎯 Landed on main 'Save and Close' via keyboard tabbing")
                break

        if not found:
            if logger:
                logger.error("  ❌ Could not reach 'Save and Close' via local tabbing")
            return False

        # Step 3: Now press Space exactly as in manual testing
        page.wait_for_timeout(100)
        page.keyboard.press("Space")

        if logger:
            logger.info("  ✅ Pressed Space on focused 'Save and Close' button (keyboard path)")

        # Step 4: Watch for either a successful close OR an Oracle error dialog.
        #
        # Oracle surfaces validation failures (e.g. missing Date) via a global
        # dialog with id ending in 'msgDlg'. If that appears, we should treat
        # Save & Close as FAILED and surface the message in logs.
        success = False
        max_wait_ms = 10000
        poll_ms = 500
        waited = 0

        while waited < max_wait_ms:
            # 4a) Check for Oracle error dialog
            try:
                err = page.locator("div[id$='msgDlg']").first
                if err.is_visible(timeout=200):
                    # Extract condensed error text
                    try:
                        msg_body = page.locator("div[id$='msgDlg::_cnt']").first.inner_text()
                    except Exception:
                        msg_body = "<unable to read error body>"

                    if logger:
                        logger.error(f"❌ Oracle error dialog after Save and Close: {msg_body}")

                    # Try to click OK to dismiss so the user can see the page
                    try:
                        err.locator("button[id$='msgDlg::cancel']").first.click(timeout=2000)
                    except Exception:
                        pass

                    return False
            except Exception:
                # If locator itself fails, just continue polling
                pass

            # 4b) Check if the form has actually closed (StartDate gone)
            try:
                page.wait_for_selector(
                    "input[id*='StartDate']", state="hidden", timeout=poll_ms
                )
                success = True
                break
            except Exception:
                # Still visible; keep waiting
                waited += poll_ms

        if success:
            if logger:
                logger.info("✅ Save and Close completed - form closed successfully")
            return True

        # Timed out without seeing either success or an explicit error dialog.
        # Do one last network-idle wait and warn the user.
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        if logger:
            logger.warning("⚠️  Save and Close may not have completed (no close, no error dialog detected)")
        return False

    except Exception as e:
        if logger:
            logger.error(f"Could not click main 'Save and Close' button: {e}")
        return False

