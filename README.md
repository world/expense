## AI‑Powered Oracle Expense Reports 💰

AI‑powered helper that turns batches of receipt images into **pre‑filled Oracle expense reports** using LLM **vision models** (Claude / OpenAI) with a local Tesseract OCR fallback, plus Playwright automation to click through Oracle for you. It also learns your **home city** and infers the **trip destination city** directly from the receipts.

---

## Features (high‑level)

- **Vision + OCR pipeline**
  - OpenAI/Anthropic: send receipt **images** to the provider’s vision model.
  - Custom/other: run local **Tesseract OCR**, then send OCR text to a text‑only LLM.
- **AI expense & city inference**
  - LLM returns strict JSON with: `expense_type`, `merchant`, `total_amount`, `currency`, `date`, `description`, and `city`.
  - Expense type is validated against the Oracle type list in `config.json` (with fallback to a Misc/Other type).
  - For meals, uses **time-of-day** on the receipt (when visible) to pick `Meals-Breakfast and Tip` vs `Meals-Lunch and Tip` vs `Meals-Dinner and Tip`.
  - For trip destination, compares each receipt’s inferred `city` to your configured home `airport_city` and picks the **first different city** as the destination (used in the report Purpose, e.g. `Trip to Chicago`).
- **Oracle automation (Playwright)**
  - Uses a persistent Chromium profile so your Oracle SSO session is remembered.
  - Creates a new report, then for each receipt:
    - Clicks `Create Item` / `Create Another`, fills date, type, merchant, description, amount, and attendees (for Meals).
    - Uploads the receipt file via `<input type="file">`.
  - Uses robust keyboard‑driven Tab/Space/Enter sequences to reliably trigger Oracle’s `Create Item`, `Create Another`, and `Save and Close` buttons.
- **Smart date resolution**
  - 1) Use date from OCR/LLM (if valid).
  - 2) Else reuse the last successful date.
  - 3) Else prompt you **once** on the first receipt.
- **Test mode and logging**
  - `make test` runs the entire OCR/LLM + logging pipeline **without touching Oracle**.
  - Every run appends detailed JSON lines and a human summary table to `expense_helper.log`.
- **macOS‑friendly UX**
  - Finder dialog for selecting the receipts folder.
  - Remembers your last‑used receipts folder in `~/.expense_helper_cache`.

---

## Prerequisites

### System Requirements

- **macOS** (developed and tested on macOS 12+)
- **Python 3.9+**
- **Homebrew** (for installing Tesseract and Tkinter on macOS)
- **Tesseract OCR** (used as a fallback when not using a vision provider)

You do **not** need to install Playwright browsers manually – `make setup` handles that.

### One‑Command Setup

From the project root:

```bash
cd /path/to/expense
make setup
```

This will:

- Check for Python 3
- Ensure Homebrew is installed (and tell you how to install it if not)
- Install **Tesseract OCR** (if missing)
- Ensure Python **Tkinter** is available (for the Finder dialog)
- Create a `.venv` virtual environment
- Install Python dependencies from `requirements.txt`
- Install Playwright’s **Chromium** browser

If Homebrew is missing, setup will tell you to run:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Then re‑run:

```bash
make setup
```

---

## Configuration (`config.json`)

All runtime configuration lives in `config.json`. A `config.example.json` is provided as a template.

### 1. LLM Settings

Minimal example:

```json
{
  "llm": {
    "api_key": "sk-your-api-key-here",
    "model": "gpt-4o",
    "base_url": "https://api.openai.com/v1",
    "provider": "openai"
  },
  ...
}
```

**Supported provider modes:**

- **OpenAI** (`provider: "openai"`; default `base_url: "https://api.openai.com/v1"`):
  - Uses OpenAI’s Chat Completions + Vision for receipts.
- **Anthropic** (`provider: "anthropic"`; default `base_url: "https://api.anthropic.com/v1"`):
  - Uses Claude’s Messages + Vision for receipts.
- **Other / custom OpenAI‑compatible API** (`provider: "other"`):
  - Uses a custom `base_url` with OpenAI‑compatible APIs.
  - In this mode, images go through **local Tesseract OCR** and only OCR text is sent to the LLM.

If `llm` is not fully configured, the app will:

1. Prompt you to choose a provider (OpenAI / Anthropic / Other).
2. Ask for the API key.
3. Fetch available models (when possible) and let you choose.
4. Validate connectivity with a small JSON test call.
5. Save the working configuration back into `config.json`.

You can force re‑configuration at any time with:

```bash
make test-reset   # runs in test mode and clears LLM settings first
```

### 2. Expense Types

The current `config.json` uses a **simple list of Oracle expense type labels**:

```json
"expense_types": [
  "Meals-Breakfast and Tip",
  "Meals-Lunch and Tip",
  "Meals-Dinner and Tip",
  "Travel-Hotel Accommodation",
  "Taxi",
  "Miscellaneous Other",
  "... etc ..."
]
```

**IMPORTANT:**

- Each entry must **exactly match** the text in your Oracle Expenses *Type* dropdown (e.g., `Meals-Breakfast and Tip`).
- These values are:
  - Shown to the LLM as the **allowed label list**.
  - Used directly when selecting the type in the Oracle dropdown (`select_option(label=...)`).

> The earlier JSON object format with `type_key`, `type_label`, and `keywords` is **no longer used**. The app now relies on:
> - This string list from `config.json`.
> - Hard‑coded heuristics in the prompt (e.g. hotel vs meal, rideshare vs airfare, etc.).

### 3. Page Selectors

UI selectors for Oracle live in the `page_selectors` section:

```json
"page_selectors": {
  "login_detection": { ... },
  "reports_table": { ... },
  "buttons": {
    "new_report": "text=Create Report",
    "create_item": "text=Create Item, button:has-text('Create Item')",
    "create_another": "text=Create Another, button:has-text('Create Another')",
    "save_and_close": "text=Save and Close, button:has-text('Save and Close')"
  },
  "fields": {
    "report_name": "...",
    "expense_type": "...",
    "amount": "...",
    "date": "...",
    "merchant": "...",
    "description": "...",
    "attachment_button": "...",
    "attachment_input": "input[type='file']"
  }
}
```

If Oracle’s DOM structure changes, you can adapt the automation by editing this section without touching Python code.

### 4. User Metadata

Additional fields in `config.json`:

- `"user_full_name"` – Used to auto‑fill the “Number of Attendees” and “Attendees” fields for **Meals** expense types.
- `"airport_city"` – Your “home” airport city (e.g., `"Austin"`). Used in trip‑destination detection.

If these are missing, `main.py` will prompt you once and then persist them back into `config.json`.

---

## Usage

### Core Make Commands

From the project root:

- **Setup** (once per machine):

  ```bash
  make setup
  ```

- **Test mode** (no Oracle changes, recommended first run):

  ```bash
  make test
  ```

- **Test mode + reset LLM configuration**:

  ```bash
  make test-reset
  ```

- **Normal run (creates items in Oracle)**:

  ```bash
  make run
  ```

- **Verbose run (extra logging, raw OCR/LLM in log)**:

  ```bash
  make run-verbose
  ```

You can see all available commands with:

```bash
make help
```

### What Happens When You Run It

1. **Configuration + LLM bootstrap**
   - Loads `config.json`.
   - Ensures LLM is configured and reachable; prompts if not.
   - Ensures `user_full_name` and `airport_city` are set.

2. **Select receipts folder**
   - Prompts you to:
     - Accept the last‑used folder.
     - Enter a path manually.
     - Or (on macOS with Tkinter) open a **Finder** dialog.
   - Recalls the last used folder via `~/.expense_helper_cache`.

3. **Scan receipts**
   - Collects `.jpg`, `.jpeg`, `.png`, `.heic` files in the chosen folder.
   - Logs skipped non-image files.

4. **LLM / OCR analysis per receipt**
   - For **OpenAI/Anthropic**:
     - Encodes the image to base64 and sends it to the provider’s **vision API**.
   - For **other** providers:
     - Runs **local Tesseract OCR**, then sends just the text to the LLM.
   - Prompt logic:
     - Returns a strict JSON object with:
       - `expense_type`, `merchant`, `total_amount`, `currency`, `date`, `description`, `city`.
     - For meals, uses **time-of-day** (when visible) to choose:
       - `< 11:00` → `Meals-Breakfast and Tip`
       - `11:00–16:00` → `Meals-Lunch and Tip`
       - `> 16:00` → `Meals-Dinner and Tip`
   - `parse_llm_response`:
     - Ensures required fields are present.
     - Normalizes/validates the date into `DD-MM-YYYY`.
     - Normalizes amount to a positive float.
     - If the `expense_type` is not one of the configured `expense_types`, falls back to a “Misc/Other” type if available.

5. **Date resolution**
   - If the LLM date is valid (DD-MM-YYYY), it is used.
   - Otherwise:
     - For subsequent receipts: reuses the **last successful** date.
     - For the first receipt with no date: prompts you interactively.

6. **Trip Destination and Report Creation**
   - Before creating items, the app pre‑analyzes receipts:
     - It scans for the first receipt whose `city` differs from your `airport_city`.
     - Uses that as the trip destination, falling back to `"Business Travel"` if none found.
   - It then:
     - Starts Playwright with a persistent Chromium context.
     - Navigates to the configured Oracle URL.
     - Waits for you to log in (if necessary).
     - Creates a **new report** with Purpose: `Trip to <destination>`.

7. **Oracle item creation**
   - For each receipt (in non‑test mode):
     - For the first item, clicks **Create Item**; for subsequent ones, uses **Create Another**.
     - Fills:
       - Date (converted to Oracle’s `DD-MMM-YYYY` format).
       - Type (via `<select>` with `ExpenseTypeId`).
       - For “Meals-*” types:
         - Sets `Number of Attendees = 1`.
         - Sets `Attendees` to your full name.
       - Waits for the attachment drop‑zone to appear.
       - Uploads the image via a hidden `<input type="file">`.
       - Fills amount, merchant, and description.
   - **Button clicking reliability:**
     - Oracle’s buttons (`Create Another`, `Save and Close`) use `<a class="xrg" role="button">` with `onclick="this.focus();return false"`, which makes normal `.click()` unreliable.
     - The helper:
       - Tabs from the “Create Expense Item” label.
       - Detects focus landing on the target button.
       - Sends **Space (with a small hold) and then Enter** to reliably trigger the action.

8. **Save and Close**
   - For the **last receipt**, the helper:
     - Triggers **Save and Close** on the item form.
   - The main report stays open in the browser so you can review or submit manually.

9. **Summary & logs**
   - At the end:
     - Prints a formatted table of all receipts (date, type, merchant, description, amount).
     - Prints totals per currency.
     - Writes structured JSON lines for each receipt and a final summary object to `expense_helper.log`.
   - In non‑test mode, leaves the browser open and prompts:
     - “Browser left open for you to review/complete. Press Enter here when you're done to close the browser.”

---

## Folder Structure

```text
expense/
├── main.py              # CLI entrypoint and orchestration wiring
├── config.py            # Config loading, LLM bootstrap, selectors
├── logging_utils.py     # Structured logging + summary output
├── ocr_llm.py           # Vision/OCR + LLM pipeline and response parsing
├── browser_agent.py     # Playwright automation for Oracle UI
├── expense_workflow.py  # High-level receipt processing workflow
├── config.json          # Your live config (LLM, expense types, selectors, user info)
├── config.example.json  # Template config for sharing
├── requirements.txt     # Python dependencies
├── Makefile             # Setup, run, and maintenance targets
├── QUICKSTART.md        # Short “5 minute” setup guide
└── README.md            # This document
```

---

## Logs

All runs append to `expense_helper.log`:

- One JSON line per receipt with:
  - `filename`, `index`, `expense_type`, `total_amount`, `currency`, `merchant`, `description`, `date`, `date_source`, `warnings`, `status`.
- A final JSON summary line:
  - `type: "run_summary"`, `total_receipts_processed`, `receipts_skipped`, and `total_by_currency`.
- A human‑friendly console table plus totals.

In **verbose** mode (`make run-verbose` or `--verbose`), additional raw data is stored in the per‑receipt JSON entries:

- `raw_ocr` (Tesseract output when used)
- `raw_llm_response` (raw JSON from the LLM)

---

## Troubleshooting

### LLM connection failed

- Check your API key and model in `config.json`.
- Verify `base_url` and `provider`:
  - OpenAI: `https://api.openai.com/v1`, `provider: "openai"`.
  - Anthropic: `https://api.anthropic.com/v1`, `provider: "anthropic"`.
  - Custom: your own base URL, `provider: "other"`.
- Re-run with:

  ```bash
  make test-reset
  ```

  to force re‑entering LLM settings.

### “Could not find selector” / UI automation issues

- Oracle’s UI or labels may have changed.
- Update `page_selectors` in `config.json` to match the current DOM.
- Run with verbose logging:

  ```bash
  make run-verbose
  ```

  and inspect `expense_helper.log` plus the live browser to see what the script is doing.

### OCR/LLM extracts bad data

- Ensure receipts are:
  - Upright (not rotated).
  - Legible (not too dark or blurry).
  - High enough resolution.
- Use `make test` or `make run-verbose` to see:
  - Raw OCR text (`raw_ocr`).
  - Raw LLM JSON (`raw_llm_response`).

---

## Distribution

To create a shareable package for another Mac user:

```bash
make dist
```

This creates `dist/expense-helper-YYYYMMDD.tar.gz` containing all source code and configs (but not your API keys or receipts).

On another Mac:

1. Extract:

   ```bash
   tar -xzf expense-helper-YYYYMMDD.tar.gz
   ```

2. Run setup:

   ```bash
   make setup
   ```

3. Edit `config.json` with your LLM credentials and Oracle URL.
4. Run:

   ```bash
   make test
   ```

   then:

   ```bash
   make run
   ```

---

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

### CLI Flags (see `main.py`)

- `--test` – test mode (no Oracle writes).
- `--verbose` – verbose logging.
- `--reset-llm` – clear LLM settings and reconfigure.
- `--config` – path to a specific `config.json`.

---

## Security Notes

- **API Keys**
  - Never commit `config.json` with real API keys to version control.
  - The helper stores keys only in your local `config.json`.
- **Receipts & data privacy**
  - For **OpenAI / Anthropic providers**, receipt images (or their base64 encodings) are sent to the provider’s **vision API** for processing.
  - For `provider: "other"`, images stay local; only OCR’d text is sent to the LLM.
  - The app does *not* send receipts anywhere else.
- **Browser automation**
  - Playwright runs in **headed** (visible) mode so you can see every action.
  - A persistent browser profile under `~/.expense_helper_browser` keeps your Oracle SSO session.

---

## License

MIT License – feel free to modify and distribute.

---

## Support / Debugging Checklist

1. Check `expense_helper.log` for errors and summary.
2. If automation mis-clicks, run `make run-verbose` and watch the live browser.
3. Verify Oracle labels and selectors match those in `config.json`.
4. Reconfigure the LLM via `make test-reset` if model/API issues appear.

**Happy expense reporting!** 🎉

