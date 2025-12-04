# Oracle Expense Helper 💰

Automate your Oracle expense report creation using OCR + AI to extract information from receipt images.

## Features

- 🖼️ **OCR Processing**: Extracts text from receipt images using Tesseract
- 🤖 **AI-Powered**: Uses LLM (GPT-4/Claude/etc.) to intelligently categorize and extract expense details
- 🌐 **Browser Automation**: Playwright automatically fills Oracle Expenses forms and uploads receipt images
- 📅 **Smart Date Resolution**: Extracts dates from receipts, with intelligent fallbacks
- 📊 **Comprehensive Logging**: Detailed per-receipt logs and summary totals
- 🧪 **Test Mode**: Preview OCR+LLM results without touching Oracle
- 🍎 **macOS Optimized**: Finder integration for easy folder selection

## Prerequisites

### System Requirements

- **macOS** (tested on macOS 12+)
- **Python 3.9+**
- **Tesseract OCR**
- **Homebrew** (recommended)

### Installation

**One-command setup:**

```bash
cd /path/to/expense
make setup
```

This automatically:
- Checks for Python 3 (exit with instructions if missing)
- Installs Tesseract OCR via Homebrew (if not already installed)
- Creates a Python virtual environment
- Installs all Python dependencies
- Installs Playwright's Chromium browser

**If you don't have Homebrew**, the setup will prompt you to install it first:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Then just run `make setup` again.

## Configuration

All configuration is in a single `config.json` file.

### 1. LLM Settings

Edit `config.json` and add your LLM API credentials:

```json
{
  "llm": {
    "api_key": "sk-your-api-key-here",
    "model": "gpt-4",
    "base_url": "https://api.openai.com/v1"
  },
  ...
}
```

**Supported LLM Providers:**
- OpenAI (GPT-4, GPT-3.5)
- Anthropic Claude (use compatible base URL)
- Any OpenAI-compatible API

> **Note**: If you don't configure this, the app will prompt you for the values on first run and offer to save them.

### 2. Expense Types

The default `config.json` includes common expense types:
- Meals
- Transportation
- Lodging
- Office Supplies
- Other

You can customize these in `config.json` under the `expense_types` array.

### 3. Page Selectors

If Oracle's UI changes, you can update the CSS/XPath selectors in the `page_selectors` section of `config.json` without touching any code.

## Usage

### Basic Usage

1. **Prepare your receipts**: Put all receipt images (JPG, PNG, HEIC) in a folder

2. **Run the helper**:
   ```bash
   make run
   ```

3. **Follow the prompts**:
   - Select your receipts folder (via Finder or type path)
   - The LLM connection will be tested
   - A browser will open to Oracle Expenses
   - Log in if needed (the script waits for you)
   - The script will process each receipt and create expense items

### Test Mode (Recommended First Run)

To see what the app would do without actually modifying Oracle:

```bash
make test
```

This runs OCR + LLM and shows you the extracted information, totals, and any warnings.

### Verbose Mode

For detailed debugging and to see raw OCR text and LLM responses:

```bash
make run-verbose
```

## Workflow

1. **Date Selection**: 
   - First tries to extract date from receipt via OCR+LLM
   - If not found, uses the date from the previous receipt
   - If it's the first receipt and no date found, prompts you once

2. **Receipt Analysis**:
   - OCR extracts text from image
   - LLM chooses expense type, extracts merchant, amount, description

3. **Oracle Integration**:
   - Opens browser to Oracle Expenses
   - Detects existing in-progress report or creates new one
   - For each receipt:
     - Clicks "Create Item" (first) or "Create Another"
     - Fills type, amount, date, merchant, description
     - Clicks "Add Attachment" and uploads the receipt image
   - Clicks "Save and Close" after last receipt

4. **Summary**:
   - Shows total amounts by currency
   - Logs all details to `expense_helper.log`

## Folder Structure

```
expense/
├── main.py                  # CLI entrypoint
├── config.py                # Configuration management
├── logging_utils.py         # Structured logging
├── ocr_llm.py              # OCR + LLM processing
├── browser_agent.py        # Playwright automation
├── expense_workflow.py     # Orchestration logic
├── config.json             # All configuration (LLM, types, selectors)
├── config.example.json     # Template for sharing
├── requirements.txt        # Python dependencies
├── Makefile               # Setup and run commands
└── README.md              # This file
```

## Logs

All runs are logged to `expense_helper.log` with:
- Per-receipt JSON entries (machine-readable)
- Human-readable summaries
- Warnings and errors
- In verbose mode: raw OCR text and LLM responses

## Troubleshooting

### "LLM connection failed"
- Check your API key in `config.json`
- Verify the `base_url` is correct for your provider
- Check your internet connection

### "Could not find selector"
- Oracle's UI may have changed
- Update the `page_selectors` section in `config.json` with current selectors
- Run with `--verbose` to see what the browser sees

### OCR extracts garbage text
- Ensure receipt images are clear and well-lit
- Try higher resolution images
- Check `expense_helper.log` in verbose mode to see raw OCR output

## Distribution

To create a shareable package for another Mac user:

```bash
make dist
```

This creates `dist/expense-helper-YYYYMMDD.tar.gz` containing all source code and configs (but not your API keys or receipts).

**To use the package on another Mac:**
1. Extract: `tar -xzf expense-helper-YYYYMMDD.tar.gz`
2. Run: `make setup`
3. Edit `config.json` with your LLM credentials
4. Run: `make run`

## Advanced Usage

### Custom config file

```bash
.venv/bin/python main.py --config my_config.json
```

### Direct Python invocation

```bash
source .venv/bin/activate
python main.py --test --verbose
```

## Security Notes

- **API Keys**: Never commit `config.json` with real API keys to version control
- **Receipts**: The app does not upload receipt images anywhere; OCR runs locally
- **Browser**: Playwright runs in headed (visible) mode so you can see what's happening

## License

MIT License - feel free to modify and distribute.

## Support

For issues or questions:
1. Check `expense_helper.log` for detailed error messages
2. Run with `--verbose` for debugging
3. Verify Oracle's UI hasn't changed (update the `page_selectors` section in `config.json` if needed)

---

**Happy expense reporting!** 🎉

