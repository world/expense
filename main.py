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


# Supported image formats
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic'}


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


def collect_receipt_images(folder: Path, logger: ExpenseLogger) -> List[Path]:
    """
    Scan folder for supported image files.
    
    Args:
        folder: Path to receipts folder
        logger: Logger instance
        
    Returns:
        List of image file paths
    """
    logger.info(f"Scanning for receipt images in: {folder}")
    
    images = []
    skipped = []
    
    for file_path in sorted(folder.iterdir()):
        if file_path.is_file():
            ext = file_path.suffix.lower()
            if ext in SUPPORTED_EXTENSIONS:
                images.append(file_path)
            else:
                skipped.append(file_path.name)
    
    logger.info(f"Found {len(images)} receipt image(s)")
    
    if skipped:
        logger.debug(f"Skipped {len(skipped)} non-image file(s)")
    
    if not images:
        logger.warning(f"No supported image files found in {folder}")
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
    
    # Select receipts folder
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
                browser_agent.stop()
                sys.exit(1)
            
            # Wait for login
            if not browser_agent.wait_for_login():
                logger.error("Login failed or timed out. Exiting.")
                browser_agent.stop()
                sys.exit(1)
            
            # Check for existing report or create new
            existing = browser_agent.find_existing_report()
            if existing:
                logger.info("Using existing in-progress report")
                # Click into it
                try:
                    existing.click()
                except:
                    pass
            else:
                # Create new report
                report_name = f"Expenses {receipt_paths[0].stem if receipt_paths else 'Report'}"
                if not browser_agent.create_new_report(report_name):
                    logger.error("Failed to create new report. Exiting.")
                    browser_agent.stop()
                    sys.exit(1)
            
            # Scrape and verify expense types from Oracle
            logger.info("Verifying expense types from Oracle...")
            scraped_types = browser_agent.scrape_expense_types()
            
            if scraped_types:
                # Compare with config
                configured_labels = [et['type_label'] for et in config.get_expense_types()]
                
                # Check if there are new types in Oracle not in config
                new_types = [t for t in scraped_types if t not in configured_labels]
                missing_types = [t for t in configured_labels if t not in scraped_types]
                
                if new_types or missing_types:
                    logger.warning(f"⚠️  Expense type mismatch detected!")
                    if new_types:
                        logger.warning(f"   New types in Oracle: {new_types}")
                    if missing_types:
                        logger.warning(f"   Types in config.json not in Oracle: {missing_types}")
                    
                    update = input("\nUpdate config.json with current Oracle types? [Y/n]: ").strip().lower()
                    if update != 'n':
                        # Build new expense_types list
                        updated_types = []
                        for label in scraped_types:
                            # Try to find existing config for this type
                            existing = next((et for et in config.get_expense_types() if et['type_label'] == label), None)
                            if existing:
                                updated_types.append(existing)
                            else:
                                # New type - create basic entry
                                type_key = label.upper().replace(' ', '_').replace('-', '_').replace('(', '').replace(')', '')
                                updated_types.append({
                                    "type_key": type_key,
                                    "type_label": label
                                })
                        
                        # Update config
                        config.config_data['expense_types'] = updated_types
                        config.save_config()
                        logger.info(f"✅ Updated config.json with {len(updated_types)} expense types from Oracle")
                else:
                    logger.info("✅ Expense types match Oracle")
            else:
                logger.warning("⚠️  Could not verify expense types from Oracle, using config.json as-is")
        
        except Exception as e:
            logger.error(f"Browser initialization failed: {e}")
            if browser_agent:
                browser_agent.stop()
            sys.exit(1)
    
    # Create workflow
    workflow = ExpenseWorkflow(
        receipt_processor=receipt_processor,
        browser_agent=browser_agent,
        logger=logger,
        test_mode=args.test
    )
    
    # Process all receipts
    try:
        success = workflow.process_all_receipts(receipt_paths)
        
        if not success:
            logger.error("No receipts were successfully processed")
            if browser_agent:
                browser_agent.stop()
            sys.exit(1)
        
        logger.info("\n✅ Expense processing complete!")
        
        if args.test:
            logger.info("(Test mode - no changes made to Oracle)")
        
    except KeyboardInterrupt:
        logger.warning("\n\n⚠️  Interrupted by user")
    except Exception as e:
        logger.error(f"\n❌ Unexpected error: {e}")
        import traceback
        logger.debug(traceback.format_exc())
    finally:
        # Cleanup
        if browser_agent:
            logger.info("Closing browser...")
            browser_agent.stop()
    
    logger.info("Done!")


if __name__ == '__main__':
    main()

