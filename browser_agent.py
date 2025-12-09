"""
Playwright-based browser automation for Oracle Expenses.
Refactored into modular helpers.
"""
import os
from typing import Optional, List, Tuple

from playwright.sync_api import sync_playwright, Page, Playwright

# Import all our modular helpers
from browser_login import (
    wait_for_login as _wait_for_login,
    find_unsubmitted_report as _find_unsubmitted_report,
    create_new_report as _create_new_report,
    scan_existing_items as _scan_existing_items
)
from browser_buttons import (
    click_create_item as _click_create_item,
    click_create_another as _click_create_another,
    click_save_and_close as _click_save_and_close
)
from browser_dropdowns import (
    select_expense_type as _select_expense_type
)
from browser_fields import (
    fill_date_field as _fill_date_field,
    fill_amount_field as _fill_amount_field,
    fill_description_field as _fill_description_field,
    fill_merchant_field as _fill_merchant_field,
    upload_receipt_attachment as _upload_receipt_attachment
)
from browser_airfare import fill_airfare_fields as _fill_airfare_fields
from browser_hotels import (
    fill_hotel_nightly_breakdown as _fill_hotel_nightly_breakdown,
    fill_hotel_nightly_breakdown_ai as _fill_hotel_nightly_breakdown_ai,
)
from browser_meals import fill_meals_attendee_fields as _fill_meals_attendee_fields


class OracleBrowserAgent:
    """Manages browser automation for Oracle Expenses UI."""
    
    def __init__(self, config, logger=None):
        self.config = config
        self.logger = logger
        self.playwright: Optional[Playwright] = None
        self.browser = None
        self.context = None
        self.page: Optional[Page] = None
        self.is_logged_in = False
        
        # User metadata from config (loaded once at init)
        self.user_full_name = config.config_data.get('user_full_name', '')
        self.airport_city = config.config_data.get('airport_city', '')
        self.travel_agency = config.config_data.get('travel_agency', 'AMEX GBT')
    
    def start(self):
        """Start Playwright with persistent session (remembers login)."""
        self.playwright = sync_playwright().start()
        
        # Use persistent context - saves cookies/session between runs
        user_data_dir = os.path.expanduser("~/.expense_helper_browser")
        
        if self.logger:
            self.logger.info("🚀 Launching browser (session will be remembered)...")
            self.logger.info(f"   Session data stored in: {user_data_dir}")
        
        # Launch with persistent context
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            viewport={'width': 1400, 'height': 900},
            accept_downloads=True,
            ignore_https_errors=True,
            bypass_csp=True,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
        """Navigate to Oracle Expenses URL."""
        url = self.config.get_oracle_url()
        
        if self.logger:
            self.logger.info("🌐 Navigating to Oracle Expenses...")
        
        try:
            self.page.goto(url, wait_until='networkidle', timeout=30000)
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to navigate: {e}")
            return False
    
    def wait_for_login(self) -> bool:
        """Wait for user to complete login."""
        if self.logger:
            self.logger.info("Checking if logged in...")
        
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
                    if self.page.locator(selector).first.is_visible(timeout=1000):
                        return True
                except:
                    pass
            return False
        
        if check_logged_in():
            if self.logger:
                self.logger.info("✅ Already logged in!")
            return True
        
        # Look for Okta FastPass button - try most common first (it's usually an <a> tag)
        try:
            self.page.locator("a:has-text('Sign in with Okta FastPass')").first.click(timeout=3000)
            if self.logger:
                self.logger.info("🔘 Clicked Okta FastPass button")
            self.page.wait_for_load_state("domcontentloaded")
        except:
            # Button not present or different selector, continue
            if self.logger:
                self.logger.info("ℹ️  No Okta FastPass button found")
        
        # Wait for manual login if needed
        if self.logger:
            self.logger.info("⏳ Waiting for login... (you have 60 seconds)")
            self.logger.info("   Please log in manually in the browser window.")
        
        # Poll for login completion
        import time
        start = time.time()
        timeout_ms = 60000
        while (time.time() - start) < (timeout_ms / 1000):
            if check_logged_in():
                if self.logger:
                    self.logger.info("✅ Login detected!")
                return True
            time.sleep(2)
        
        if self.logger:
            self.logger.error(f"Login timeout after {timeout_ms/1000}s")
        return False
    
    def find_unsubmitted_report(self) -> bool:
        """
        Find an existing unsubmitted report and click on it.
        
        Returns:
            True if found and opened
        """
        found, _ = _find_unsubmitted_report(self.page, self.logger)
        return found
    
    def scan_existing_items(self) -> List:
        """
        Scan the currently opened report for existing items.
        
        Returns:
            List of dicts with 'amount' and 'merchant' keys
        """
        return _scan_existing_items(self.page, self.logger)
    
    def create_new_report(self, purpose: str) -> bool:
        """
        Create a new expense report.
        
        Args:
            purpose: Report purpose
            
        Returns:
            True if successfully created
        """
        return _create_new_report(self.page, purpose, self.logger)
    
    def navigate_and_login(self) -> bool:
        """
        Navigate to Oracle and wait for login (combined).
        
        Returns:
            True if successfully logged in
        """
        url = self.config.get_oracle_url()
        return _wait_for_login(self.page, url, self.logger)
    
    def find_or_create_report(self, purpose: str) -> Tuple[bool, List]:
        """
        Find an existing unsubmitted report or create a new one (combined).
        
        Args:
            purpose: Report purpose for new report
            
        Returns:
            Tuple of (success, existing_items)
        """
        # Try to find existing unsubmitted report
        found, existing_items = _find_unsubmitted_report(self.page, self.logger)
        
        if found:
            return (True, existing_items)
        
        # Create new report
        success = _create_new_report(self.page, purpose, self.logger)
        return (success, [])
    
    def scrape_expense_types(self) -> List[str]:
        """
        Scrape available expense types from Oracle UI.
        
        Returns:
            List of expense type labels
        """
        if self.logger:
            self.logger.info("📋 Scraping expense types from Oracle UI...")
        
        # Click Create Item to reveal expense type dropdown
        _click_create_item(self.page, self.logger)
        
        # Scrape expense types
        expense_types = {}
        type_selector = "select[id*='ExpenseTypeId'], select[id*='expenseType'], select[id*='ItemType']"
        
        try:
            type_loc = self.page.locator(type_selector).first
            type_loc.wait_for(state="visible", timeout=5000)
            
            # Click to load options
            type_loc.click()
            self.page.wait_for_timeout(500)
            
            # Get all options
            options = type_loc.locator("option").all()
            
            for opt in options:
                try:
                    value = opt.get_attribute("value")
                    label = opt.get_attribute("title") or opt.inner_text()
                    
                    if value and value != "0" and label:
                        expense_types[label.strip()] = value
                        
                except Exception:
                    continue
            
            if self.logger:
                self.logger.info(f"✅ Found {len(expense_types)} expense types")
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to scrape expense types: {e}")
        
        # Return list of keys when dict, for compatibility
        if isinstance(expense_types, dict):
            return list(expense_types.keys())
        return expense_types
    
    def create_expense_item(
        self,
        date: str,
        expense_type: str,
        amount: float,
        merchant: str = "",
        description: str = "",
        receipt_path: str = "",
        is_first: bool = False,
        # Type-specific fields
        attendee_count: int = 0,
        attendee_names: str = "",
        flight_type: str = "",
        flight_class: str = "",
        ticket_number: str = "",
        departure_city: str = "",
        arrival_city: str = "",
        passenger_name: str = "",
        agency: str = "",
        nights: int = 0,
        check_in_date: str = "",
        check_out_date: str = ""
    ) -> bool:
        """
        Fill out expense item form with all details.
        
        Args:
            date: Date in DD-MM-YYYY format
            expense_type: Expense type label
            amount: Amount
            merchant: Merchant name
            description: Description
            receipt_path: Path to receipt image
            (Plus type-specific fields)
            
        Returns:
            True if successfully filled
        """
        if self.logger:
            self.logger.info(f"📝 Creating expense item: {expense_type}")
        
        # Click "Create Item" if this is the first item
        if is_first:
            if self.logger:
                self.logger.info("Clicking 'Create Item'...")
            
            # Use the most reliable selector (span.xrk works best)
            try:
                self.page.locator("span.xrk:has-text('Create Item')").first.click()
                if self.logger:
                    self.logger.info("✅ Clicked Create Item")
            except:
                # Fallback to simple text selector
                try:
                    self.page.locator("text=Create Item").first.click()
                    if self.logger:
                        self.logger.info("✅ Clicked Create Item (fallback)")
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"Could not find Create Item button: {e}")
                    return False
            
            # Wait for form to appear
            self.page.wait_for_load_state("domcontentloaded")
        
        # Get type-specific field requirements
        type_fields = self.config.get_expense_type_fields(expense_type)
        
        # === PHASE 1: Common fields (Date, Type, Amount) ===
        
        # 1. Date
        _fill_date_field(self.page, date, self.logger)
        
        # 2. Type
        _select_expense_type(self.page, expense_type, self.logger)
        
        # 3. Amount
        _fill_amount_field(self.page, amount, self.logger)
        
        # === PHASE 2: Receipt upload ===
        
        if receipt_path:
            _upload_receipt_attachment(self.page, receipt_path, self.logger)
        
        # === PHASE 3: Description and Merchant (always try; hotel may still have these fields) ===
        
        _fill_description_field(self.page, description, self.logger)
        _fill_merchant_field(self.page, merchant, self.logger)
        
        # === PHASE 4: Type-specific fields ===
        
        # Meals: attendee fields
        if "attendee_count" in type_fields or "attendee_names" in type_fields:
            _fill_meals_attendee_fields(self.page, self.user_full_name, self.logger)
        
        # Airfare: flight fields
        if any(f in type_fields for f in ["flight_type", "flight_class", "ticket_number", "departure_city", "arrival_city", "passenger_name", "agency"]):
            _fill_airfare_fields(
                self.page,
                flight_type=flight_type,
                flight_class=flight_class,
                ticket_number=ticket_number,
                departure_city=departure_city,
                arrival_city=arrival_city,
                # Default passenger name to the configured user_full_name if the
                # LLM/receipt did not provide one explicitly.
                passenger_name=passenger_name or self.user_full_name,
                agency=agency or self.travel_agency,
                logger=self.logger
            )
        
        # Hotel: nightly breakdown
        if "hotel_nightly_breakdown" in type_fields:
            used_ai = False

            # Only attempt the AI browser agent for Travel-Hotel Accommodation.
            if expense_type.strip().lower() == "travel-hotel accommodation".lower():
                try:
                    llm_cfg = self.config.get_llm_config()
                    llm_model = llm_cfg.get("model", "")
                    llm_provider = self.config.llm_provider or llm_cfg.get("provider", "openai")
                    llm_client = self.config.llm_client

                    if llm_client and llm_model:
                        if self.logger:
                            self.logger.info(
                                "🏨 Using AI browser agent for hotel nightly breakdown..."
                            )
                        used_ai = _fill_hotel_nightly_breakdown_ai(
                            self.page,
                            total_amount=amount,
                            base_date=date,
                            nights=nights,
                            check_in_date=check_in_date,
                            check_out_date=check_out_date,
                            llm_client=llm_client,
                            llm_model=llm_model,
                            llm_provider=llm_provider,
                            logger=self.logger,
                        )
                    else:
                        if self.logger:
                            self.logger.info(
                                "LLM client/model not available; skipping AI hotel breakdown"
                            )
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"Hotel AI nightly breakdown failed: {e}")
                    used_ai = False

            # If AI path is disabled or fails, always fall back to the legacy logic
            if not used_ai:
                if self.logger:
                    self.logger.info("🏨 Falling back to legacy hotel nightly breakdown logic")
                _fill_hotel_nightly_breakdown(
                    self.page,
                    total_amount=amount,
                    base_date=date,
                    nights=nights,
                    check_in_date=check_in_date,
                    check_out_date=check_out_date,
                    logger=self.logger
                )
        
        if self.logger:
            self.logger.info("✅ Expense item form completed")
        
        return True
    
    def click_create_item(self) -> bool:
        """Click 'Create Item' button."""
        return _click_create_item(self.page, self.logger)
    
    def click_create_another(self) -> bool:
        """Click 'Create Another' button."""
        return _click_create_another(self.page, self.logger)
    
    def click_save_and_close(self) -> bool:
        """Click 'Save and Close' button."""
        return _click_save_and_close(self.page, self.logger)
