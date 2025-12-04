# Quick Start Guide 🚀

Get your expense helper up and running in 5 minutes!

## Step 1: One-Command Setup

```bash
cd /Users/DTNR64/code/msi/expense
make setup
```

That's it! This automatically:
- Checks for Python 3
- Installs Tesseract OCR if missing (via Homebrew)
- Creates a Python virtual environment
- Installs all dependencies
- Installs the Playwright browser

**Note**: If you don't have Homebrew, the setup will tell you to install it first, then just run `make setup` again.

## Step 2: Test It Out

First, run in test mode to see what it would do:

```bash
make test
```

This will:
- **Prompt you for your LLM API key** (if not in config.json)
- Test the LLM connection
- Prompt you to select a folder with receipt images (via Finder)
- Run OCR + LLM on all receipts
- Show you the extracted data and totals
- **NOT** modify anything in Oracle

## Step 3: Run It For Real

Once you're happy with the test results:

```bash
make run
```

This will:
- Open a browser to Oracle Expenses
- Wait for you to log in (if needed)
- Process all receipts and create expense items
- Show a final summary

## Folder Structure

Put your receipt images (JPG, PNG, HEIC) in any folder, like:

```
~/Documents/receipts/
  ├── receipt1.jpg
  ├── receipt2.png
  └── receipt3.heic
```

The app will ask you to select this folder when it runs.

## Tips

- **Use Test Mode First**: Always run `make test` before `make run` to preview results
- **Check Logs**: See `expense_helper.log` for detailed per-receipt information
- **Verbose Mode**: Use `make run-verbose` to see raw OCR text and LLM responses
- **Date Handling**: The app tries to extract dates from receipts, but will prompt you if it can't find one on the first receipt

## Troubleshooting

### "LLM connection failed"
- Check your API key in `config.json`
- Make sure you have internet access

### "No receipts found"
- Make sure your folder has `.jpg`, `.png`, or `.heic` files
- Check the file extensions match (case-insensitive)

## Next Steps

See the full [README.md](README.md) for:
- Detailed configuration options
- Customizing expense types
- Updating Oracle UI selectors
- Distribution to other users

---

**Ready to go!** Run `make test` to start. 🎉

