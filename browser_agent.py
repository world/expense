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
                time.sleep(2)  # Wait for form to load
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
                    time.sleep(1)
                    
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
            # Try multiple selectors for the Create Report button
            create_selectors = [
                "text=Create Report",
                "button:has-text('Create Report')",
                "a:has-text('Create Report')",
                "[aria-label*='Create Report']",
                ".create-report"
            ]
            
            clicked = False
            for selector in create_selectors:
                try:
                    if self.page.locator(selector).first.is_visible(timeout=2000):
                        self.page.locator(selector).first.click()
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
            
            # Wait for the Create Expense Report form to load
            time.sleep(2)
            
            # Fill in the Purpose field
            if purpose:
                purpose_selectors = [
                    "input[id*='purpose' i]",
                    "input[name*='purpose' i]",
                    "input[aria-label*='Purpose' i]",
                    "label:has-text('Purpose') + input",
                    "label:has-text('Purpose') ~ input",
                    "//label[contains(text(),'Purpose')]/following::input[1]"
                ]
                
                filled = False
                for selector in purpose_selectors:
                    try:
                        if selector.startswith("//"):
                            # XPath
                            loc = self.page.locator(f"xpath={selector}")
                        else:
                            loc = self.page.locator(selector)
                        
                        if loc.first.is_visible(timeout=2000):
                            loc.first.fill(purpose)
                            filled = True
                            if self.logger:
                                self.logger.info(f"✅ Filled Purpose: {purpose}")
                            break
                    except:
                        continue
                
                if not filled:
                    if self.logger:
                        self.logger.warning("Could not find Purpose field, continuing anyway...")
            
            if self.logger:
                self.logger.info("✅ New report form ready")
            
            time.sleep(1)  # Brief pause for page to settle
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
                time.sleep(0.5)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Could not click attachment button: {e}")
                # Button might not be needed, file input might be visible
            
            # Upload file via file input
            # Wait for file input to be available
            self.page.wait_for_selector(attachment_input, timeout=10000)
            
            # Set the file
            self.page.set_input_files(attachment_input, receipt_path)
            
            # Wait a moment for upload to process
            time.sleep(1)
            
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
        is_first: bool = False
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
                
                # Try multiple selectors for Create Item button
                create_item_selectors = [
                    "text=Create Item",
                    "button:has-text('Create Item')",
                    "a:has-text('Create Item')",
                    "[aria-label*='Create Item']",
                    "span:has-text('Create Item')"
                ]
                
                clicked = False
                for selector in create_item_selectors:
                    try:
                        loc = self.page.locator(selector).first
                        if loc.is_visible(timeout=2000):
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
                
                time.sleep(2)  # Wait for form to load
            
            # Fill Date field
            if self.logger:
                self.logger.info(f"📅 Filling date: {date}")
            date_filled = False
            date_selectors = [
                "input[placeholder*='dd-mmm']",
                "input[id*='date' i]",
                "input[name*='date' i]",
                "//label[contains(text(),'Date')]/following::input[1]"
            ]
            for sel in date_selectors:
                try:
                    if sel.startswith("//"):
                        loc = self.page.locator(f"xpath={sel}")
                    else:
                        loc = self.page.locator(sel)
                    if loc.first.is_visible(timeout=2000):
                        loc.first.fill(date)
                        date_filled = True
                        break
                except:
                    continue
            if not date_filled and self.logger:
                self.logger.warning("Could not fill Date field")
            
            # Wait for type dropdown to populate after date entry
            time.sleep(0.5)
            
            # Fill Type dropdown
            if self.logger:
                self.logger.info(f"📋 Filling type: {expense_type}")
            type_filled = False
            
            # Try standard select first (quick check)
            standard_selectors = [
                "select[id*='type' i]",
                "select[name*='type' i]"
            ]
            for sel in standard_selectors:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible(timeout=500):  # Quick 500ms check
                        loc.select_option(label=expense_type)
                        type_filled = True
                        break
                except:
                    continue
            
            # Oracle often uses custom dropdown - try clicking and selecting from list
            if not type_filled:
                oracle_dropdown_selectors = [
                    "[id*='Type' i][class*='select']",
                    "[id*='type' i][role='combobox']",
                    "//label[contains(text(),'Type')]/following::*[contains(@class,'select')][1]",
                    "//label[contains(text(),'Type')]/following::input[1]"
                ]
                for sel in oracle_dropdown_selectors:
                    try:
                        if sel.startswith("//"):
                            loc = self.page.locator(f"xpath={sel}").first
                        else:
                            loc = self.page.locator(sel).first
                        if loc.is_visible(timeout=500):  # Quick check
                            loc.click()
                            time.sleep(0.3)  # Brief wait for dropdown to open
                            # Try to click the option from the dropdown list
                            option = self.page.locator(f"text={expense_type}").first
                            if option.is_visible(timeout=1000):
                                option.click()
                                type_filled = True
                                break
                    except:
                        continue
            
            if not type_filled and self.logger:
                self.logger.warning("Could not fill Type field")
            
            # Wait for attachments section to appear after type selection
            if self.logger:
                self.logger.info("⏳ Waiting for attachments section...")
            attachment_selectors = [
                "text=Attachments",
                "button:has-text('Add Attachment')",
                "button:has-text('Attach')",
                "input[type='file']"
            ]
            attachment_appeared = False
            # Try all selectors with a single shared timeout (race them)
            try:
                combined_selector = ", ".join(attachment_selectors)
                self.page.locator(combined_selector).first.wait_for(state="visible", timeout=3000)
                attachment_appeared = True
                if self.logger:
                    self.logger.info("✅ Attachments section appeared")
            except:
                # Fallback to a brief wait
                if self.logger:
                    self.logger.info("⏳ Attachments not detected, brief wait...")
                time.sleep(0.5)
            
            # Upload receipt attachment right after attachments section appears
            if receipt_path:
                if self.logger:
                    self.logger.info("📎 Uploading receipt attachment...")
                upload_success = self.upload_receipt_attachment(receipt_path)
                if not upload_success:
                    self.logger.warning("⚠️  Attachment upload failed, but continuing...")
            
            # Fill Amount field
            if self.logger:
                self.logger.info(f"💵 Filling amount: {amount}")
            amount_filled = False
            amount_selectors = [
                "input[id*='amount' i]",
                "input[name*='amount' i]",
                "//label[contains(text(),'Amount')]/following::input[1]"
            ]
            for sel in amount_selectors:
                try:
                    if sel.startswith("//"):
                        loc = self.page.locator(f"xpath={sel}")
                    else:
                        loc = self.page.locator(sel)
                    if loc.first.is_visible(timeout=2000):
                        loc.first.fill(str(amount))
                        amount_filled = True
                        break
                except:
                    continue
            if not amount_filled and self.logger:
                self.logger.warning("Could not fill Amount field")
            
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
        
        create_another_selectors = [
            "text=Create Another",
            "button:has-text('Create Another')",
            "a:has-text('Create Another')",
            "input[value*='Create Another']"
        ]
        
        try:
            for selector in create_another_selectors:
                try:
                    loc = self.page.locator(selector).first
                    if loc.is_visible(timeout=2000):
                        loc.click()
                        if self.logger:
                            self.logger.info("✅ Clicked Create Another")
                        time.sleep(2)
                        return True
                except:
                    continue
            
            if self.logger:
                self.logger.warning("Could not find 'Create Another' button")
            return False
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Create Another failed: {e}")
            return False
    
    def click_save_and_close(self) -> bool:
        """
        Click 'Save and Close' button to finish.
        
        Returns:
            True if button found and clicked
        """
        if self.logger:
            self.logger.info("💾 Clicking 'Save and Close'...")
        
        save_selectors = [
            "text=Save and Close",
            "button:has-text('Save and Close')",
            "button:has-text('Save & Close')",
            "a:has-text('Save and Close')",
            "input[value*='Save']"
        ]
        
        try:
            for selector in save_selectors:
                try:
                    loc = self.page.locator(selector).first
                    if loc.is_visible(timeout=2000):
                        loc.click()
                        if self.logger:
                            self.logger.info("✅ Clicked Save and Close")
                        time.sleep(2)
                        return True
                except:
                    continue
            
            if self.logger:
                self.logger.warning("Could not find 'Save and Close' button")
            return False
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Save and Close failed: {e}")
            return False
    

