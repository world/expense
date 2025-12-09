# AI-Powered Oracle Expense Reports 💰

Automate your Oracle expense reports with AI vision models (Claude/OpenAI) + Playwright browser automation. Drop your receipts in a folder, run one command, and watch AI fill everything out.

---

## What It Does

- **Vision AI** extracts merchant, amount, date, description, and city from receipt images
- **Smart inference**: meal type from time-of-day, trip destination by comparing cities to your home city  
- **Auto-fills Oracle**: creates report items with proper types, amounts, dates, descriptions, attachments
- **Type-specific fields**: handles Meals (attendees), Flights (ticket #, class, cities), Hotels (nightly breakdown)
- **Duplicate detection**: skips items already filed in unsubmitted reports
- **Test mode**: validates everything without touching Oracle

---

## Quick Start

```bash
# 1. Setup (installs Python deps, Playwright, Tesseract OCR)
make setup

# 2. Test run (no Oracle changes, recommended first)
make test

# 3. Real run (creates expense items)
make run
```

On first run, you'll be prompted for:
- LLM provider (OpenAI/Claude/Other) + API key
- Your home city (for trip inference)
- Full name (for meals attendee field)
- Travel agency (for flight bookings)

These are saved to `config.json`.

---

## Supported Receipt Types

| Expense Type | Fields Filled |
|-------------|---------------|
| **Meals** (Breakfast/Lunch/Dinner) | Date, Type (inferred from time), Amount, Merchant, Description, Attendees |
| **Travel-Airfare** | Date, Amount, Merchant, Description, Flight Type/Class, Ticket #, Departure/Arrival City, Passenger, Agency |
| **Travel-Hotel Accommodation** | Date, Amount, Merchant, Description + nightly breakdown (Type: Hotel Charges, per-night dates/amounts) |
| **Others** (Taxi, Misc, etc.) | Date, Type, Amount, Merchant, Description |

All types auto-attach the receipt image.

---

## Configuration

Edit `config.json`:

```json
{
  "llm": {
    "provider": "openai",           // or "anthropic" or "other"
    "api_key": "sk-...",
    "model": "gpt-4o"
  },
  "oracle_url": "https://...",
  "user_full_name": "John Doe",
  "airport_city": "Austin",         // Your home city
  "travel_agency": "AMEX GBT",      // or "OTHERS"
  "expense_types": [                // Must match Oracle dropdown labels exactly
    "Meals-Breakfast and Tip",
    "Meals-Lunch and Tip",
    "Meals-Dinner and Tip",
    "Travel-Airfare",
    "Travel-Hotel Accommodation",
    "Travel-Non-Car Rental Ground Transport",
    "Miscellaneous Other"
  ]
}
```

**Vision support:**
- `openai` / `anthropic`: sends images directly to vision API
- `other`: uses local Tesseract OCR + text-only LLM

---

## Commands

| Command | Description |
|---------|-------------|
| `make setup` | Install all dependencies (once per machine) |
| `make test` | Test mode: analyze receipts, no Oracle changes |
| `make test-reset` | Test + clear LLM config (reconfigure provider) |
| `make run` | Normal run: creates expense items in Oracle |
| `make run-verbose` | Run with full debug logging |

---

## How It Works

1. **Select folder**: Finder dialog or manual path (remembers last folder)
2. **AI analysis**: Each receipt image → LLM vision API → JSON with type, merchant, amount, date, city, description
3. **Smart inference**:
   - **Meal type**: `< 11am` = Breakfast, `11am-4pm` = Lunch, `> 4pm` = Dinner
   - **Trip city**: first receipt city ≠ home city → report Purpose: "Trip to [City]"
   - **Flight class**: International + ≥6hr = Business, else Coach
4. **Oracle automation**: Playwright logs in, creates report, fills items field-by-field, uploads receipts
5. **Review**: Browser stays open for manual review/submission

---

## Architecture

```
main.py              # CLI orchestration
config.py            # Config + LLM bootstrap
ocr_llm.py           # Vision/OCR + LLM JSON parsing
browser_agent.py     # Orchestrator for Playwright automation
  ├─ browser_login.py      # Login & session management
  ├─ browser_buttons.py    # Create Item/Another, Save & Close
  ├─ browser_dropdowns.py  # Dropdown validation & retry logic
  ├─ browser_fields.py     # Common fields (date, amount, etc.)
  ├─ browser_airfare.py    # Flight-specific fields
  ├─ browser_hotels.py     # Hotel nightly breakdown
  └─ browser_meals.py      # Meal attendee fields
expense_workflow.py  # Receipt processing pipeline
logging_utils.py     # Structured JSON + console logging
```

Every run appends to `expense_helper.log` (JSON lines + summary table).

---

## Troubleshooting

**LLM errors**: Run `make test-reset` to reconfigure provider/API key

**Oracle UI issues**: Check `page_selectors` in `config.json` if DOM changed

**Bad OCR**: Ensure images are upright, high-res, legible. Run `make run-verbose` to see raw OCR/LLM output

**Browser not clicking**: Oracle uses `onclick="return false"` buttons. Script uses Tab+Space+Enter sequences for reliability.

---

## Notes

- **Duplicate detection**: Automatically detects/skips existing items in unsubmitted reports
- **PDF support**: Converts PDFs to images locally before vision analysis
- **SSO persistence**: Uses persistent browser profile (`~/.expense_helper_browser`)
- **Date fallback**: Uses last valid date if OCR can't extract, prompts only once
- **Security**: API keys stored locally in `config.json`, images sent only to chosen LLM provider

---

**MIT License** • Happy expense reporting! 🎉
