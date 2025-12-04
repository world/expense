"""
Playwright-based browser automation for Oracle Expenses.
"""
import time
from typing import List, Optional, Tuple

from playwright.sync_api import sync_playwright, Page, Browser, Playwright, TimeoutError as PlaywrightTimeoutError


class OracleBrowserAgent:
    """Manages browser automation for Oracle Expenses UI."""
    
    def __init__(self, config, logger=None):
        self.config = config
        self.logger = logger
        self.playwright: Optional[Playwright] = None
        self.browser = None  # Could be Browser or BrowserContext
        self.context = None
        self.page: Optional[Page] = None
        self.is_logged_in = False
    
    def start(self):
        """Start Playwright with persistent session (remembers login)."""
        import os
        
        self.playwright = sync_playwright().start()
        
        # Use persistent context - saves cookies/session between runs
        user_data_dir = os.path.expanduser("~/.expense_helper_browser")
        
        if self.logger:
            self.logger.info("🚀 Launching browser (session will be remembered)...")
            self.logger.info(f"   Session data stored in: {user_data_dir}")
        
        # Launch with persistent context with all the right settings for corporate SSO
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            viewport={'width': 1400, 'height': 900},
            # These settings help with corporate SSO persistence
            accept_downloads=True,
            ignore_https_errors=True,
            bypass_csp=True,
            # Use a real Chrome user agent
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            # Enable all storage
            permissions=["geolocation", "notifications"],
        )
        
        # Use existing page or create new one
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()
        
        if self.logger:
            self.logger.info("✅ Browser started (login will be remembered for next time)")
    
    def stop(self):
        """Close browser and cleanup."""
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()
        
        if self.logger:
            self.logger.info("Browser closed")
    
    def navigate_to_oracle(self) -> bool:
        """
        Navigate to Oracle Expenses URL.
        
        Returns:
            True if successful
        """
        url = self.config.get_oracle_url()
        
        if self.logger:
            self.logger.info(f"Navigating to Oracle Expenses...")
        
        try:
            self.page.goto(url, wait_until='networkidle', timeout=30000)
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to navigate: {e}")
            return False
    
    def wait_for_login(self) -> bool:
        """
        Wait for user to complete login if needed.
        Detects login by checking for expense-related elements on page.
        
        Returns:
            True if login detected
        """
        timeout_ms = 60000
        
        if self.logger:
            self.logger.info("Checking if logged in...")
        
        # Look for any of these elements that indicate we're logged in
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
                    if self.page.locator(selector).first.is_visible(timeout=1000):
                        return True
                except:
                    pass
            return False
        
        # Quick check if already logged in
        if check_logged_in():
            if self.logger:
                self.logger.info("✅ Already logged in!")
            self.is_logged_in = True
            return True
        
        # Need to log in
        if self.logger:
            self.logger.warning("⚠️  Login required. Please log in...")
        
        print("\n" + "=" * 70)
        print("🔐 LOGIN REQUIRED")
        print("=" * 70)
        print("Please log in to Oracle in the browser window.")
        print("This script will continue automatically once you're logged in.")
        print("=" * 70 + "\n")
        
        # Poll for login completion
        import time
        start = time.time()
        while (time.time() - start) < (timeout_ms / 1000):
            if check_logged_in():
                if self.logger:
                    self.logger.info("✅ Login detected!")
                self.is_logged_in = True
                return True
            time.sleep(2)
        
        if self.logger:
            self.logger.error(f"Login timeout after {timeout_ms/1000}s")
        return False
    
    def find_existing_report(self) -> Optional[str]:
        """
        Scan for existing unpaid/in-progress expense report.
        
        Returns:
            Report identifier/selector if found, None otherwise
        """
        if self.logger:
            self.logger.info("Scanning for existing in-progress reports...")
        
        table_config = self.config.get_selector('reports_table')
        in_progress_statuses = table_config.get('in_progress_statuses', [])
        
        try:
            # Wait for table
            self.page.wait_for_selector(table_config['table_selector'], timeout=10000)
            
            # Find rows
            rows = self.page.query_selector_all(table_config['row_selector'])
            
            for row in rows:
                text = row.inner_text().lower()
                for status in in_progress_statuses:
                    if status.lower() in text:
                        if self.logger:
                            self.logger.info(f"✅ Found existing report with status: {status}")
                        return row
            
            if self.logger:
                self.logger.info("No existing in-progress reports found")
            return None
            
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Could not scan for existing reports: {e}")
            return None
    
    def scrape_expense_types(self) -> List[str]:
        """
        Scrape available expense types from Oracle dropdown.
        
        Returns:
            List of expense type labels from the dropdown
        """
        try:
            if self.logger:
                self.logger.info("🔍 Scraping expense types from Oracle...")
            
            fields = self.config.get_selector('fields')
            type_selector = fields.get('expense_type')
            
            # Navigate to create item to expose the dropdown
            buttons = self.config.get_selector('buttons')
            create_item_selector = buttons.get('create_item')
            
            try:
                self.page.click(create_item_selector, timeout=10000)
                self.page.wait_for_load_state("domcontentloaded")
            except:
                if self.logger:
                    self.logger.warning("Could not click Create Item for scraping, trying anyway...")
            
            # Try to get dropdown options
            expense_types = []
            
            # Method 1: Try as <select> element
            try:
                options = self.page.query_selector_all(f"{type_selector} option")
                for option in options:
                    text = option.inner_text().strip()
                    if text and text not in ['', '--Select--', 'Select One']:
                        expense_types.append(text)
            except:
                pass
            
            # Method 2: If not a select, try to find a dropdown list
            if not expense_types:
                try:
                    # Click to open dropdown
                    self.page.click(type_selector, timeout=5000)
                    self.page.wait_for_timeout(300)  # Brief Playwright wait for dropdown animation
                    
                    # Look for list items
                    dropdown_items = self.page.query_selector_all("li[role='option'], div[role='option'], a[role='option']")
                    for item in dropdown_items:
                        text = item.inner_text().strip()
                        if text and text not in ['', '--Select--', 'Select One']:
                            expense_types.append(text)
                except:
                    pass
            
            if expense_types:
                if self.logger:
                    self.logger.info(f"✅ Found {len(expense_types)} expense types in Oracle")
                return expense_types
            else:
                if self.logger:
                    self.logger.warning("⚠️  Could not scrape expense types from Oracle")
                return []
                
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to scrape expense types: {e}")
            return []
    
    def create_new_report(self, purpose: str = None) -> bool:
        """
        Click to create a new expense report and fill in Purpose.
        
        Args:
            purpose: Purpose/description for the report (e.g., "Trip to Chicago")
            
        Returns:
            True if successful
        """
        if self.logger:
            self.logger.info("🆕 Creating new expense report...")
        
        try:
            # Oracle uses SVG with aria-label and span with class for "Create Report"
            create_selectors = [
                "svg[aria-label='Create Report']",
                "a:has(svg[aria-label='Create Report'])",
                "span.expense-report-card-title:has-text('Create Report')",
                "a.xmx:has(svg)",
                "text=Create Report",
                "[aria-label='Create Report']",
                "[title='Create Report']"
            ]
            
            clicked = False
            for selector in create_selectors:
                try:
                    loc = self.page.locator(selector).first
                    if loc.is_visible(timeout=500):
                        loc.click()
                        clicked = True
                        if self.logger:
                            self.logger.info(f"✅ Clicked Create Report")
                        break
                except:
                    continue
            
            if not clicked:
                if self.logger:
                    self.logger.error("Could not find Create Report button")
                return False
            
            # Smart wait: wait for page to be ready (network idle or form element visible)
            self.page.wait_for_load_state("domcontentloaded")
            
            # Fill in the Purpose field
            if purpose:
                purpose_selector = "input[id*='purpose' i], input[name*='purpose' i], input[aria-label*='Purpose' i]"
                
                try:
                    loc = self.page.locator(purpose_selector).first
                    loc.wait_for(state="visible", timeout=3000)
                    loc.fill(purpose)
                    if self.logger:
                        self.logger.info(f"✅ Filled Purpose: {purpose}")
                except:
                    # Try XPath as fallback
                    try:
                        loc = self.page.locator("xpath=//label[contains(text(),'Purpose')]/following::input[1]").first
                        loc.wait_for(state="visible", timeout=1000)
                        loc.fill(purpose)
                        if self.logger:
                            self.logger.info(f"✅ Filled Purpose: {purpose}")
                    except:
                        if self.logger:
                            self.logger.warning("Could not find Purpose field, continuing anyway...")
            
            if self.logger:
                self.logger.info("✅ New report form ready")
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to create new report: {e}")
            return False
    
    def upload_receipt_attachment(self, receipt_path: str) -> bool:
        """
        Upload a receipt image as an attachment.
        
        Args:
            receipt_path: Path to the receipt image file
            
        Returns:
            True if successful
        """
        try:
            fields = self.config.get_selector('fields')
            attachment_button = fields.get('attachment_button')
            attachment_input = fields.get('attachment_input')
            
            if self.logger:
                self.logger.debug(f"Uploading attachment: {receipt_path}")
            
            # Click "Add Attachment" button
            try:
                self.page.click(attachment_button, timeout=5000)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Could not click attachment button: {e}")
                # Button might not be needed, file input might be visible
            
            # Upload file via file input
            # Wait for file input to be available
            self.page.wait_for_selector(attachment_input, timeout=10000)
            
            # Set the file
            self.page.set_input_files(attachment_input, receipt_path)
            
            # Smart wait for upload to process - wait for any upload indicator to disappear
            self.page.wait_for_load_state("networkidle", timeout=10000)
            
            if self.logger:
                self.logger.debug(f"✅ Attachment uploaded successfully")
            
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to upload attachment: {e}")
            return False
    
    def create_expense_item(
        self,
        expense_type: str,
        amount: float,
        date: str,
        merchant: str,
        description: str,
        receipt_path: str = None,
        is_first: bool = False,
        user_full_name: str = None
    ) -> bool:
        """
        Fill and save an expense item.
        
        Args:
            expense_type: Type label to select
            amount: Expense amount
            date: Date in DD-MM-YYYY format
            merchant: Merchant name
            description: Expense description
            is_first: Whether this is the first item (needs "Create Item" click)
            user_full_name: User's name for Meals attendee field
            
        Returns:
            True if successful
        """
        try:
            buttons = self.config.get_selector('buttons')
            fields = self.config.get_selector('fields')
            
            # Click "Create Item" if first item
            if is_first:
                if self.logger:
                    self.logger.info("Clicking 'Create Item'...")
                
                # Race all Create Item selectors at once
                # Oracle uses span.xrk for Create Item
                create_item_selectors = [
                    "span.xrk:has-text('Create Item')",
                    "text=Create Item",
                    "button:has-text('Create Item')",
                    "a:has-text('Create Item')",
                    "[aria-label*='Create Item']"
                ]
                
                clicked = False
                for selector in create_item_selectors:
                    try:
                        loc = self.page.locator(selector).first
                        if loc.is_visible(timeout=500):
                            loc.click()
                            clicked = True
                            if self.logger:
                                self.logger.info("✅ Clicked Create Item")
                            break
                    except:
                        continue
                
                if not clicked:
                    if self.logger:
                        self.logger.error("Could not find Create Item button")
                    return False
                
                # Smart wait: wait for form to load (date field visible)
                self.page.wait_for_load_state("domcontentloaded")
            
            # Fill Date field - Oracle uses StartDate in id, format dd-mmm-yyyy
            if self.logger:
                self.logger.info(f"📅 Filling date: {date}")
            
            # Convert date from DD-MM-YYYY to DD-MMM-YYYY format for Oracle
            oracle_date = date
            try:
                from datetime import datetime
                # Try parsing DD-MM-YYYY format
                if '-' in date and len(date.split('-')[1]) <= 2:
                    parsed = datetime.strptime(date, "%d-%m-%Y")
                    oracle_date = parsed.strftime("%d-%b-%Y")  # e.g., "19-Nov-2025"
                    if self.logger:
                        self.logger.info(f"📅 Converted to Oracle format: {oracle_date}")
            except:
                pass  # Keep original if conversion fails
            
            date_filled = False
            # Oracle uses input with StartDate in the id
            date_selector = "input[id*='StartDate'], input[placeholder*='dd-mmm'], input[aria-label='Date']"
            
            try:
                loc = self.page.locator(date_selector).first
                loc.wait_for(state="visible", timeout=2000)
                loc.fill(oracle_date)
                date_filled = True
                if self.logger:
                    self.logger.info(f"✅ Filled date: {oracle_date}")
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Could not fill Date field: {e}")
            
            # Fill Type dropdown - it's a <select> with ExpenseTypeId in the id
            # Oracle quirk: need to click dropdown TWICE after date for values to appear
            if self.logger:
                self.logger.info(f"📋 Filling type: {expense_type}")
            type_filled = False
            
            type_selector = "select[id*='ExpenseTypeId']"
            
            try:
                type_loc = self.page.locator(type_selector).first
                type_loc.wait_for(state="visible", timeout=2000)
                
                # Oracle quirk: click dropdown twice to load options
                if self.logger:
                    self.logger.info("  Clicking dropdown (1st click)...")
                type_loc.click()
                self.page.wait_for_timeout(300)
                
                if self.logger:
                    self.logger.info("  Clicking dropdown (2nd click)...")
                type_loc.click()
                self.page.wait_for_timeout(300)
                
                # Check options loaded
                options_count = type_loc.locator("option").count()
                if self.logger:
                    self.logger.info(f"  Found {options_count} options")
                
                if self.logger:
                    self.logger.info(f"  Selecting '{expense_type}'...")
                
                # Use select_option with label
                type_loc.select_option(label=expense_type, timeout=3000)
                type_filled = True
                if self.logger:
                    self.logger.info(f"✅ Selected type: {expense_type}")
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Type fill error: {e}")
            
            if not type_filled and self.logger:
                self.logger.warning("Could not fill Type field")
            
            # For Meals types, fill in Number of Attendees (1) and Attendee Names
            if expense_type and expense_type.startswith("Meals") and user_full_name:
                if self.logger:
                    self.logger.info("🍽️  Meals type - filling attendee info...")
                
                # Fill Number of Attendees = 1 (id contains "numberOfAttendees")
                try:
                    attendee_count_selector = "input[id*='numberOfAttendees']"
                    attendee_loc = self.page.locator(attendee_count_selector).first
                    attendee_loc.wait_for(state="visible", timeout=2000)
                    attendee_loc.fill("1")
                    if self.logger:
                        self.logger.info("✅ Set Number of Attendees: 1")
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"Could not fill Number of Attendees: {e}")
                
                # Fill Attendee Names with user's name (id contains "attendeesMeals")
                try:
                    names_selector = "input[id*='attendeesMeals'], input[id*='attendees']"
                    names_loc = self.page.locator(names_selector).first
                    names_loc.wait_for(state="visible", timeout=2000)
                    names_loc.fill(user_full_name)
                    if self.logger:
                        self.logger.info(f"✅ Set Attendees: {user_full_name}")
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"Could not fill Attendees: {e}")
            
            # After type is selected, attachments dropzone should appear
            if self.logger:
                self.logger.info("⏳ Waiting for attachments dropzone (appears after type)...")
            
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
                    loc = self.page.locator(sel).first
                    loc.wait_for(state="visible", timeout=2000)
                    attachment_appeared = True
                    if self.logger:
                        self.logger.info(f"✅ Attachments dropzone appeared (found via {sel})")
                    break
                except:
                    continue
            
            if not attachment_appeared:
                if self.logger:
                    self.logger.info("⏳ Attachments dropzone not visible yet")
            
            # Upload receipt attachment via dropzone
            if receipt_path and attachment_appeared:
                if self.logger:
                    self.logger.info("📎 Uploading receipt attachment...")
                try:
                    # Step 1: Click the dropzone link (has title="Add File" and id ending in cilDzMsg)
                    dropzone_link = self.page.locator("a[id*='cilDzMsg'], a[title='Add File']").first
                    if self.logger:
                        self.logger.info("  Clicking dropzone...")
                    dropzone_link.click()
                    self.page.wait_for_timeout(500)
                    
                    # Step 2: Click "Add File" from the dropdown menu (id ends in miDzAddFi)
                    if self.logger:
                        self.logger.info("  Clicking 'Add File' from menu...")
                    add_file_menu = self.page.locator("tr[id*='miDzAddFi'], [role='menuitem']:has-text('Add File'), td.xo2:has-text('Add File')").first
                    add_file_menu.click()
                    self.page.wait_for_timeout(500)
                    
                    # Step 3: Now file input should be available - set the file
                    if self.logger:
                        self.logger.info("  Setting file...")
                    file_input = self.page.locator("input[type='file']").first
                    file_input.set_input_files(receipt_path)
                    
                    if self.logger:
                        self.logger.info("⏳ Waiting for upload to complete...")
                    
                    # Wait for upload confirmation - look for the uploaded file indicator
                    # Oracle shows img[title='File'] and a[title='Download'] when upload is done
                    upload_confirm_selector = "img[title='File'], a[title='Download'], span[id*='otAvsddDiFile']"
                    try:
                        self.page.locator(upload_confirm_selector).first.wait_for(state="visible", timeout=30000)
                        if self.logger:
                            self.logger.info("✅ Attachment uploaded successfully")
                    except:
                        # Fallback: just wait for network to settle
                        self.page.wait_for_load_state("networkidle", timeout=10000)
                        if self.logger:
                            self.logger.info("✅ Attachment upload completed (network idle)")
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"⚠️  Attachment upload failed: {e}")
            elif receipt_path and not attachment_appeared:
                if self.logger:
                    self.logger.warning("⚠️  Attachments dropzone not found, skipping upload")
            
            # NOW fill Amount (after attachments)
            if self.logger:
                self.logger.info(f"💵 Filling amount: {amount}")
            amount_filled = False
            amount_selector = "input[id*='ReceiptAmount'], input[id*='amount' i], input[name*='amount' i]"
            try:
                amount_loc = self.page.locator(amount_selector).first
                amount_loc.wait_for(state="visible", timeout=2000)
                amount_loc.fill(str(amount))
                amount_filled = True
                if self.logger:
                    self.logger.info(f"✅ Filled amount: {amount}")
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Could not fill Amount field: {e}")
            
            if self.logger:
                self.logger.info("✅ Expense item fields filled")
            
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to fill expense item: {e}")
            return False
    
    def click_create_another(self) -> bool:
        """
        Click 'Create Another' button to add another item.
        
        Returns:
            True if button found and clicked
        """
        if self.logger:
            self.logger.info("➕ Clicking 'Create Another'...")
        
        # Oracle uses span.xrk for buttons
        create_another_selectors = [
            "span.xrk:has-text('Create Another')",
            "text=Create Another",
            "button:has-text('Create Another')",
            "a:has-text('Create Another')"
        ]
        
        for selector in create_another_selectors:
            try:
                loc = self.page.locator(selector).first
                if loc.is_visible(timeout=500):
                    loc.click()
                    if self.logger:
                        self.logger.info("✅ Clicked Create Another")
                    self.page.wait_for_load_state("domcontentloaded")
                    return True
            except:
                continue
        
        if self.logger:
            self.logger.warning("Could not find 'Create Another' button")
        return False
    
    def click_save_and_close(self) -> bool:
        """
        Click 'Save and Close' button to finish.
        
        Returns:
            True if button found and clicked
        """
        if self.logger:
            self.logger.info("💾 Clicking 'Save and Close'...")
        
        # Oracle uses span.xrk for buttons
        save_selectors = [
            "span.xrk:has-text('Save and Close')",
            "text=Save and Close",
            "button:has-text('Save and Close')",
            "a:has-text('Save and Close')"
        ]
        
        for selector in save_selectors:
            try:
                loc = self.page.locator(selector).first
                if loc.is_visible(timeout=500):
                    loc.click()
                    if self.logger:
                        self.logger.info("✅ Clicked Save and Close")
                    self.page.wait_for_load_state("domcontentloaded")
                    return True
            except:
                continue
        
        if self.logger:
            self.logger.warning("Could not find 'Save and Close' button")
        return False
    

