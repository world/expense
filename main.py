#!/usr/bin/env python3
"""
Oracle Expense Helper - CLI entrypoint
Automates expense report creation from receipt images.
"""
import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

# Try to import tkinter for Finder dialog, but make it optional
try:
    from tkinter import Tk, filedialog
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False

from config import Config
from logging_utils import ExpenseLogger
from ocr_llm import ReceiptProcessor
from browser_agent import OracleBrowserAgent
from expense_workflow import ExpenseWorkflow
from debug_utils import set_debug_dump_html


# Supported image and document formats
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic', '.pdf'}


def get_last_used_folder() -> Optional[Path]:
    """Get the last used receipts folder from cache."""
    cache_file = Path.home() / ".expense_helper_cache"
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                last_path = f.read().strip()
                if last_path and Path(last_path).exists():
                    return Path(last_path)
                elif last_path:
                    # Path was saved but no longer exists
                    print(f"ℹ️  Previous folder no longer exists: {last_path}")
        except Exception as e:
            print(f"⚠️  Could not read folder preference: {e}")
    return None

def save_last_used_folder(folder_path: Path):
    """Save the last used folder to cache."""
    cache_file = Path.home() / ".expense_helper_cache"
    try:
        with open(cache_file, 'w') as f:
            f.write(str(folder_path))
        print(f"💾 Remembered folder for next time: {folder_path}")
    except Exception as e:
        print(f"⚠️  Could not save folder preference: {e}")
        pass  # Don't fail if we can't save

def select_receipts_folder() -> Path:
    """
    Prompt user to select receipts folder using macOS Finder.
    
    Returns:
        Path to selected folder
    """
    # Try to get last used folder, fallback to Documents
    last_used = get_last_used_folder()
    default_path = last_used if last_used else (Path.home() / "Documents")
    
    print("\n📁 SELECT RECEIPTS FOLDER")
    print("=" * 70)
    if last_used:
        print(f"Default: {default_path} (last used)")
    else:
        print(f"Default: {default_path}")
    print()
    print("Options:")
    print("  1. Press Enter to use default")
    print("  2. Type a custom path")
    if HAS_TKINTER:
        print("  3. Type 'f' to open Finder and browse")
    print("=" * 70)
    
    choice = input("Your choice: ").strip()
    
    if not choice:
        # Use default
        folder_path = default_path
    elif choice.lower() == 'f' and HAS_TKINTER:
        # Open Finder dialog
        print("\n🖱️  Opening Finder dialog...")
        
        # Create root window with better focus handling for macOS
        root = Tk()
        root.withdraw()  # Hide the root window
        
        # Force window to front on macOS
        root.lift()
        root.attributes('-topmost', True)
        root.focus_force()
        
        # Brief pause to let window system catch up
        root.update()
        
        folder_path = filedialog.askdirectory(
            initialdir=str(default_path),
            title="Select Receipts Folder",
            parent=root
        )
        
        # Clean up
        root.attributes('-topmost', False)
        root.destroy()
        
        if not folder_path:
            print("❌ No folder selected. Exiting.")
            sys.exit(1)
        
        folder_path = Path(folder_path)
    elif choice.lower() == 'f' and not HAS_TKINTER:
        print("❌ Finder dialog not available (tkinter not installed)")
        print("Please type the folder path instead:")
        choice = input("Path: ").strip()
        folder_path = Path(choice).expanduser()
    else:
        # Custom path
        folder_path = Path(choice).expanduser()
    
    # Validate
    if not folder_path.exists():
        print(f"\n❌ Folder not found: {folder_path}")
        sys.exit(1)
    
    if not folder_path.is_dir():
        print(f"\n❌ Not a directory: {folder_path}")
        sys.exit(1)
    
    print(f"\n✅ Using folder: {folder_path}")
    
    # Save for next time
    save_last_used_folder(folder_path)
    
    return folder_path


def pdf_to_images(pdf_path: Path, logger: ExpenseLogger) -> List[Path]:
    """
    Convert PDF pages to image files in the same folder as the PDF.
    
    Args:
        pdf_path: Path to PDF file
        logger: Logger instance
        
    Returns:
        List of paths to image files (one per page)
    """
    import fitz  # PyMuPDF
    
    images = []
    
    try:
        doc = fitz.open(pdf_path)
        logger.info(f"Converting {len(doc)} page(s) from PDF: {pdf_path.name}")
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            
            # Render page to image at 300 DPI for good quality
            pix = page.get_pixmap(dpi=300)
            
            # Save in same folder as PDF with descriptive name
            if len(doc) == 1:
                # Single page: just replace .pdf with .png
                image_path = pdf_path.with_suffix('.png')
            else:
                # Multiple pages: add page number
                image_path = pdf_path.parent / f"{pdf_path.stem}_page{page_num+1}.png"
            
            # Save as PNG
            pix.save(str(image_path))
            images.append(image_path)
            
            logger.debug(f"  Converted page {page_num + 1}/{len(doc)} to {image_path.name}")
        
        doc.close()
        logger.info(f"✅ Converted PDF to {len(images)} image(s)")
        
    except Exception as e:
        logger.error(f"Failed to convert PDF {pdf_path.name}: {e}")
        # Clean up any images created so far
        for img in images:
            if img.exists():
                img.unlink()
        return []
    
    return images


def collect_receipt_images(folder: Path, logger: ExpenseLogger) -> List[Path]:
    """
    Scan folder for supported image and PDF files.
    PDFs are converted to images (one image per page) saved in the same folder.
    
    Args:
        folder: Path to receipts folder
        logger: Logger instance
        
    Returns:
        List of image file paths (including converted PDF pages)
    """
    logger.info(f"Scanning for receipts in: {folder}")
    
    images = []
    skipped = []
    
    for file_path in sorted(folder.iterdir()):
        if file_path.is_file():
            ext = file_path.suffix.lower()
            if ext == '.pdf':
                # Convert PDF to images in the same folder
                pdf_images = pdf_to_images(file_path, logger)
                images.extend(pdf_images)
            elif ext in SUPPORTED_EXTENSIONS:
                images.append(file_path)
            else:
                skipped.append(file_path.name)
    
    logger.info(f"Found {len(images)} receipt image(s)")
    
    if skipped:
        logger.debug(f"Skipped {len(skipped)} non-supported file(s)")
    
    if not images:
        logger.warning(f"No supported files found in {folder}")
        logger.info(f"Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}")
    
    return images


def main():
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Oracle Expense Helper - Automate expense report creation from receipts"
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test mode: run OCR+LLM without modifying Oracle'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose/debug logging'
    )
    parser.add_argument(
        '--reset-llm',
        action='store_true',
        help='Clear saved LLM settings and reconfigure from scratch'
    )
    parser.add_argument(
        '--config',
        default='config.json',
        help='Path to config.json (default: config.json)'
    )
    parser.add_argument(
        '-f',
        '--use-default-folder',
        action='store_true',
        help='Use last-used/default receipts folder without prompting'
    )
    parser.add_argument(
        '-d',
        '--dump-html',
        action='store_true',
        help='Enable debug mode: dump page HTML snapshots when requested'
    )
    
    args = parser.parse_args()
    
    # Banner
    print("\n" + "=" * 70)
    print("💰 ORACLE EXPENSE HELPER")
    print("=" * 70)
    if args.test:
        print("⚠️  TEST MODE: No changes will be made to Oracle")
        print("=" * 70)
    print()
    
    # Setup logging
    logger = ExpenseLogger(verbose=args.verbose)
    logger.info("Starting Oracle Expense Helper...")
    
    # Configure global debug HTML flag
    set_debug_dump_html(args.dump_html)
    
    # Load configuration
    logger.info("Loading configuration...")
    config = Config(config_path=args.config)
    
    success, error = config.load()
    if not success:
        logger.error(error)
        sys.exit(1)
    
    logger.info("✅ Configuration loaded")
    
    # Reset LLM settings if requested
    if args.reset_llm:
        logger.info("🔄 Resetting LLM configuration...")
        config.config_data['llm'] = {
            'api_key': '',
            'model': '',
            'base_url': '',
            'provider': ''
        }
        config.save_config()
        logger.info("✅ LLM settings cleared. You will be prompted to reconfigure.")
    
    # Bootstrap LLM
    if not config.bootstrap_llm(logger):
        logger.error("Cannot proceed without working LLM connection")
        sys.exit(1)
    
    # Get user's full name from config (ask if not set) - needed for Meals attendee field
    user_full_name = config.config_data.get('user_full_name', '')
    if not user_full_name:
        print("\n" + "=" * 60)
        print("👤 USER NAME SETUP")
        print("=" * 60)
        user_full_name = input("What is your full name? (e.g., John Smith): ").strip()
        if user_full_name:
            config.config_data['user_full_name'] = user_full_name
            config.save_config()
            logger.info(f"✅ Saved user name: {user_full_name}")
    
    # Get airport city from config (ask if not set) - needed for Purpose field
    airport_city = config.config_data.get('airport_city', '')
    if not airport_city:
        print("\n" + "=" * 60)
        print("🏠 AIRPORT CITY SETUP")
        print("=" * 60)
        airport_city = input("What airport city do you call home? (e.g., Austin, Boston): ").strip()
        if airport_city:
            config.config_data['airport_city'] = airport_city
            config.save_config()
            logger.info(f"✅ Saved airport city: {airport_city}")
    
    # Get travel agency from config (ask if not set) - needed for Airfare expenses
    travel_agency = config.config_data.get('travel_agency', '')
    if not travel_agency:
        print("\n" + "=" * 60)
        print("✈️  TRAVEL AGENCY SETUP")
        print("=" * 60)
        print("When you fly, what agency do you use?")
        print("  1. AMEX GBT (default)")
        print("  2. OTHERS")
        print("=" * 60)
        
        while True:
            agency_choice = input("Choose [1]: ").strip()
            
            if not agency_choice or agency_choice == "1":
                travel_agency = "AMEX GBT"
                break
            elif agency_choice == "2":
                travel_agency = "OTHERS"
                break
            else:
                print("❌ Invalid choice. Please enter 1 or 2.")
        
        config.config_data['travel_agency'] = travel_agency
        config.save_config()
        logger.info(f"✅ Saved travel agency: {travel_agency}")
    
    # Select receipts folder
    if args.use_default_folder:
        last_folder = get_last_used_folder()
        if last_folder and last_folder.exists() and last_folder.is_dir():
            print(f"\n✅ Using folder (from cache): {last_folder}")
            receipts_folder = last_folder
        else:
            # Fall back to interactive selection if cache missing/invalid
            receipts_folder = select_receipts_folder()
    else:
        receipts_folder = select_receipts_folder()
    
    # Collect receipt images
    receipt_paths = collect_receipt_images(receipts_folder, logger)
    
    if not receipt_paths:
        logger.error("No receipts to process. Exiting.")
        sys.exit(1)
    
    # Initialize components
    logger.info("Initializing OCR and LLM processor...")
    receipt_processor = ReceiptProcessor(
        llm_client=config.llm_client,
        model=config.get_llm_config()['model'],
        expense_types=config.get_expense_types(),
        provider=config.llm_provider or "openai",
        logger=logger
    )
    
    # Initialize browser agent (skip in test mode)
    browser_agent = None
    if not args.test:
        logger.info("Initializing browser automation...")
        browser_agent = OracleBrowserAgent(config=config, logger=logger)
        
        try:
            browser_agent.start()
            
            # Navigate to Oracle
            if not browser_agent.navigate_to_oracle():
                logger.error("Failed to navigate to Oracle. Exiting.")
                sys.exit(1)
            
            # Wait for login
            if not browser_agent.wait_for_login():
                logger.error("Login failed or timed out. Exiting.")
                sys.exit(1)
            
            # Check for existing unsubmitted report first
            found_existing = browser_agent.find_unsubmitted_report()
            existing_items_to_load = []
            
            if found_existing:
                # Scan existing items to avoid duplicates
                existing_items_to_load = browser_agent.scan_existing_items()
            else:
                # Pre-analyze receipts to find first city that's NOT your airport city
                trip_destination: Optional[str] = None
                logger.info("Analyzing receipts for trip destination...")
                
                for receipt_path in receipt_paths:
                    data, _, _, _ = receipt_processor.analyze_receipt(receipt_path)
                    if data:
                        user_airport = config.config_data.get('airport_city', '')
                        
                        # For flight receipts, prefer arrival_city as destination
                        if 'airfare' in data.get('expense_type', '').lower():
                            arrival_city = data.get('arrival_city', '').strip()
                            if arrival_city and arrival_city.lower() != user_airport.lower():
                                trip_destination = arrival_city
                                logger.info(f"✅ Found trip destination from flight: {arrival_city}")
                                break
                        
                        # Otherwise use generic city field
                        city = data.get('city', '').strip()
                        if city and city.lower() != user_airport.lower():
                            trip_destination = city
                            logger.info(f"✅ Found trip destination: {city}")
                            break
                
                # Create new report with purpose
                if trip_destination:
                    purpose = f"Trip to {trip_destination}"
                else:
                    # Ambiguous/non-travel receipts → generic purpose
                    purpose = "Expense Report"
                if not browser_agent.create_new_report(purpose):
                    logger.error("Failed to create new report. Exiting.")
                    sys.exit(1)
            
            # Skip scraping - use expense types from config.json
            logger.info(f"Using {len(config.get_expense_types())} expense types from config.json")
        
        except Exception as e:
            logger.error(f"Browser initialization failed: {e}")
            sys.exit(1)
    
    # Create workflow
    workflow = ExpenseWorkflow(
        receipt_processor=receipt_processor,
        browser_agent=browser_agent,
        logger=logger,
        test_mode=args.test,
        user_full_name=config.config_data.get('user_full_name', ''),
        travel_agency=config.config_data.get('travel_agency', 'AMEX GBT')
    )
    
    # Load existing items if we found an unsubmitted report
    if not args.test and existing_items_to_load:
        workflow.existing_items = existing_items_to_load
    
    # Process all receipts
    try:
        success = workflow.process_all_receipts(receipt_paths)
        
        if not success:
            logger.error("No receipts were successfully processed")
            sys.exit(1)
        
        # Check if all receipts were duplicates
        if workflow.receipts_duplicate > 0 and workflow.receipts_processed == 0:
            print("\n✅ All receipts were already filed. No action taken.")
        else:
            print("\n✅ Expense processing complete!")
        
        if args.test:
            logger.info("(Test mode - no changes made to Oracle)")
        
    except KeyboardInterrupt:
        logger.warning("\n\n⚠️  Interrupted by user")
    except Exception as e:
        logger.error(f"\n❌ Unexpected error: {e}")
        import traceback
        logger.debug(traceback.format_exc())
    
    # Keep browser open for user to review/complete
    if browser_agent and not args.test:
        print("\n" + "=" * 60)
        print("🌐 Browser left open for you to review/complete.")
        print("   Press Enter here when you're done to close the browser.")
        print("=" * 60)
        try:
            input()  # Wait for user to press Enter - keeps browser alive
        except (EOFError, KeyboardInterrupt):
            pass


if __name__ == '__main__':
    main()

