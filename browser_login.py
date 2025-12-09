"""
Login and session management for Oracle Expenses.
"""
from playwright.sync_api import Page


def wait_for_login(page: Page, url: str, logger=None) -> bool:
    """
    Navigate to Oracle and wait for user to complete login.
    
    Args:
        page: Playwright page
        url: Oracle expenses URL
        logger: Optional logger
        
    Returns:
        True if login successful
    """
    if logger:
        logger.info("🌐 Navigating to Oracle Expenses...")
    
    try:
        page.goto(url, wait_until='networkidle', timeout=30000)
    except Exception as e:
        if logger:
            logger.error(f"Failed to navigate to {url}: {e}")
        return False
    
    return wait_for_login_no_nav(page, logger)


def wait_for_login_no_nav(page: Page, logger=None) -> bool:
    """
    Wait for user to complete login (without navigation).
    Used when page has already been navigated to.
    
    Args:
        page: Playwright page
        logger: Optional logger
        
    Returns:
        True if login successful
    """
    # Ensure page is fully loaded
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except:
        pass
    
    # Small wait for any dynamic content
    page.wait_for_timeout(1000)
    
    # Check if already logged in
    login_indicators = [
        "text=Expense Reports", 
        "text=Travel and Expenses", 
        "text=Create Report",
        "text=Create Item",
        "text=Available Expense Items"
    ]
    
    def check_logged_in():
        for selector in login_indicators:
            try:
                if page.locator(selector).first.is_visible(timeout=500):
                    return True
            except:
                continue
        return False
    
    if check_logged_in():
        if logger:
            logger.info("✅ Already logged in!")
        return True
    
    # Look for Okta FastPass button
    if logger:
        logger.info("🔍 Looking for Okta FastPass button...")
        logger.info(f"   Current URL: {page.url}")
    
    # Debug: log all buttons on the page
    if logger:
        try:
            buttons = page.locator("button, a[role='button'], input[type='submit']").all()
            logger.info(f"   Found {len(buttons)} buttons/links on page:")
            for i, btn in enumerate(buttons[:10]):  # Show first 10
                try:
                    text = btn.inner_text()[:50] or btn.get_attribute("value") or btn.get_attribute("aria-label") or ""
                    if text:
                        logger.info(f"     {i+1}. {text}")
                except:
                    pass
        except Exception as e:
            logger.info(f"   Could not enumerate buttons: {e}")
    
    # Try multiple selectors for the Okta button
    okta_selectors = [
        "button:has-text('Sign in with Okta FastPass')",
        "button:has-text('Okta FastPass')",
        "a:has-text('Sign in with Okta FastPass')",
        "a:has-text('Okta FastPass')",
        "[data-se='oktafastpass']",
        "button[data-se-button='true']:has-text('Okta')",
        "input[type='submit'][value*='Okta']",
        "button:has-text('Okta')",
        "a:has-text('Okta')"
    ]
    
    okta_clicked = False
    for selector in okta_selectors:
        try:
            okta_btn = page.locator(selector).first
            if okta_btn.is_visible(timeout=1000):
                if logger:
                    logger.info(f"🔘 Found Okta button via selector: {selector}")
                    logger.info("   Clicking...")
                okta_btn.click()
                page.wait_for_load_state("domcontentloaded")
                if logger:
                    logger.info("✅ Clicked Okta FastPass button")
                    logger.info("⏳ Waiting for Okta authentication...")
                # Give Okta time to authenticate
                page.wait_for_timeout(3000)
                okta_clicked = True
                break
        except Exception:
            continue
    
    if not okta_clicked and logger:
        logger.info("ℹ️  Okta FastPass button not found (tried multiple selectors)")
    
    # Check again if now logged in (after Okta)
    if check_logged_in():
        if logger:
            logger.info("✅ Login successful!")
        return True
    
    # Wait for manual login
    if logger:
        logger.info("⏳ Waiting for login... (you have 60 seconds)")
        logger.info("   Please log in manually in the browser window.")
    
    try:
        # Wait for any login indicator to appear
        page.locator(", ".join(login_indicators)).first.wait_for(state="visible", timeout=60000)
        
        # Extra wait for page to fully load
        page.wait_for_load_state("domcontentloaded")
        
        if logger:
            logger.info("✅ Login detected!")
        return True
        
    except Exception as e:
        if logger:
            logger.error(f"Login timeout or failed: {e}")
        return False


def find_unsubmitted_report(page: Page, logger=None):
    """
    Look for an existing unsubmitted expense report and click on it.
    
    Args:
        page: Playwright page
        logger: Optional logger
        
    Returns:
        Tuple of (success: bool, existing_items: list)
    """
    if logger:
        logger.info("🔍 Checking for existing unsubmitted report...")
    
    try:
        # Look for "Not Submitted" text in the reports table
        not_submitted_loc = page.locator("span.x2ic:has-text('Not Submitted')").first
        
        if not_submitted_loc.is_visible(timeout=3000):
            if logger:
                logger.info("✅ Found existing 'Not Submitted' report, opening it...")
            
            # Click on the report row
            not_submitted_loc.click()
            page.wait_for_load_state("domcontentloaded")
            
            # Scan for existing items in the report
            existing_items = scan_existing_items(page, logger)
            
            return (True, existing_items)
        else:
            if logger:
                logger.info("No unsubmitted report found, will create new one")
            return (False, [])
            
    except Exception as e:
        if logger:
            logger.warning(f"Could not scan for existing reports: {e}")
        return (False, [])


def scan_existing_items(page: Page, logger=None) -> list:
    """
    Scan an opened expense report for existing items (amount, merchant, date).
    
    Args:
        page: Playwright page
        logger: Optional logger
        
    Returns:
        List of dicts with 'amount', 'merchant', and 'date' keys
    """
    import re
    existing_items = []
    
    if logger:
        logger.info("📋 Scanning existing expense items...")
    
    try:
        # Wait for page to fully load
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1000)
        
        # Try to find expense item divs with a timeout
        # Each expense item is in a div with class "xjb"
        try:
            # Wait for at least one item div to appear (or timeout after 3s)
            page.wait_for_selector("div.xjb[data-afrrk]", timeout=3000, state="visible")
            item_divs = page.locator("div.xjb[data-afrrk]").all()
        except:
            # No items found, report is empty
            if logger:
                logger.info("✅ No existing items found (report is empty)")
            return existing_items
        
        if logger:
            logger.debug(f"Found {len(item_divs)} potential expense item divs")
        
        for idx, item_div in enumerate(item_divs):
            try:
                # Extract DATE: Look for span.xnk with date pattern
                date = ""
                try:
                    date_span = item_div.locator("span.xnk").first
                    date_text = date_span.text_content(timeout=1000).strip()
                    # Check if it matches date pattern (e.g., "19-Nov-2025")
                    if re.match(r'\d{1,2}-[A-Z][a-z]{2}-\d{4}', date_text):
                        date = date_text
                except:
                    pass
                
                # Extract AMOUNT: Look for span.xni.xmu or span.xmu
                amount = None
                try:
                    amount_span = item_div.locator("span.xni.xmu, span.xmu").first
                    amount_text = amount_span.text_content(timeout=1000).strip()
                    # Extract numeric value
                    amount_match = re.search(r'(\d+[,\d]*\.?\d*)', amount_text)
                    if amount_match:
                        clean_amount = amount_match.group(1).replace(',', '')
                        amount = float(clean_amount)
                except:
                    pass
                
                # Extract MERCHANT: Look for span with id containing 'otn' and class 'x25'
                merchant = ""
                try:
                    merchant_span = item_div.locator("span[id*='otn']").locator("span.x25").first
                    merchant = merchant_span.text_content(timeout=1000).strip()
                except:
                    pass
                
                # Extract DESCRIPTION: Look for textarea with id containing 'outputText'
                description = ""
                try:
                    desc_textarea = item_div.locator("textarea[id*='outputText']").first
                    description = desc_textarea.input_value(timeout=1000).strip()
                except:
                    pass
                
                # Only add if we found at least an amount
                if amount is not None and amount >= 0.01:
                    existing_items.append({
                        'amount': amount,
                        'merchant': merchant,
                        'date': date,
                        'description': description
                    })
                    
                    if logger:
                        logger.info(f"  Found: {date} | ${amount:.2f} | {merchant} | {description}")
                        
            except Exception as e:
                if logger:
                    logger.debug(f"Error parsing expense item {idx}: {e}")
                continue
        
        if logger:
            logger.info(f"✅ Found {len(existing_items)} existing items")
        
    except Exception as e:
        if logger:
            logger.warning(f"Error scanning existing items: {e}")
    
    return existing_items


def create_new_report(page: Page, purpose: str, logger=None) -> bool:
    """
    Create a new expense report with the given purpose.
    
    Args:
        page: Playwright page
        purpose: Report purpose (e.g., "Trip to Chicago")
        logger: Optional logger
        
    Returns:
        True if successfully created
    """
    if logger:
        logger.info(f"📝 Creating new expense report: {purpose}")

    # Click "Create Report" - use the robust multi-selector strategy that worked pre-refactor
    create_selectors = [
        "a:has(svg[aria-label='Create Report'])",
        "svg[aria-label='Create Report']",
        "span.expense-report-card-title:has-text('Create Report')",
        "a.xmx:has(svg)",
        "text=Create Report",
        "[aria-label='Create Report']",
        "[title='Create Report']",
        "svg:has(path.svg-icon07)",
    ]

    clicked = False
    for selector in create_selectors:
        try:
            loc = page.locator(selector).first
            if loc.is_visible(timeout=500):
                loc.click()
                clicked = True
                if logger:
                    logger.info(f"✅ Clicked Create Report via selector: {selector}")
                break
        except Exception:
            continue

    if not clicked:
        if logger:
            logger.error("Could not find Create Report button")
        return False

    # Smart wait: wait for page to be ready
    page.wait_for_load_state("domcontentloaded")

    # Fill in the Purpose field (required for your workflow)
    if purpose:
        purpose_selector = (
            "input[id*='purpose' i], "
            "input[name*='purpose' i], "
            "input[aria-label*='Purpose' i]"
        )

        filled = False
        try:
            loc = page.locator(purpose_selector).first
            loc.wait_for(state="visible", timeout=3000)
            loc.fill(purpose)
            filled = True
            if logger:
                logger.info(f"✅ Filled Purpose: {purpose}")
        except Exception:
            # Fallback: label-based XPath, same as pre-refactor
            try:
                loc = page.locator(
                    "xpath=//label[contains(text(),'Purpose')]/following::input[1]"
                ).first
                loc.wait_for(state="visible", timeout=1000)
                loc.fill(purpose)
                filled = True
                if logger:
                    logger.info(f"✅ Filled Purpose via label XPath: {purpose}")
            except Exception:
                if logger:
                    logger.warning("Could not find Purpose field, continuing anyway...")

    page.wait_for_load_state("domcontentloaded")

    if logger:
        logger.info("✅ New report form ready")

    return True

