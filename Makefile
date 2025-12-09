.PHONY: help venv playwright-install setup test run clean dist

# Default Python command
PYTHON := python3
VENV := .venv
VENV_BIN := $(VENV)/bin
VENV_PYTHON := $(VENV_BIN)/python

help:
	@echo "Oracle Expense Helper - Makefile Commands"
	@echo "=========================================="
	@echo ""
	@echo "Setup commands:"
	@echo "  make setup              - Complete setup (venv + dependencies + Playwright)"
	@echo "  make venv               - Create virtual environment and install dependencies"
	@echo "  make playwright-install - Install Playwright browser (Chromium)"
	@echo ""
	@echo "Run commands:"
	@echo "  make run                - Run the expense helper (normal mode)"
	@echo "  make run-f              - Run using last-used receipts folder (no prompt)"
	@echo "  make run-f-debug        - Same as run-f, but with HTML debug dumps enabled (-d)"
	@echo "  make test               - Run in test mode (no Oracle changes)"
	@echo "  make test-reset         - Test mode + reset LLM settings"
	@echo "  make run-verbose        - Run with verbose/debug logging"
	@echo ""
	@echo "Maintenance commands:"
	@echo "  make check-deps         - Check for required system dependencies"
	@echo "  make clean              - Remove venv, cache, and log files"
	@echo "  make dist               - Create distributable package"
	@echo ""

venv:
	@echo "Creating virtual environment..."
	$(PYTHON) -m venv $(VENV)
	@echo "Installing Python dependencies..."
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -r requirements.txt
	@echo ""
	@echo "✅ Virtual environment created!"
	@echo ""
	@echo "To activate manually, run:"
	@echo "  source $(VENV_BIN)/activate"
	@echo ""

playwright-install:
	@echo "Installing Playwright Chromium browser..."
	$(VENV_PYTHON) -m playwright install chromium
	@echo "✅ Playwright browser installed!"
	@echo ""

check-deps:
	@echo "Checking system dependencies..."
	@echo ""
	@command -v $(PYTHON) >/dev/null 2>&1 || { \
		echo "❌ Python 3 not found."; \
		echo "   Install from: https://www.python.org/downloads/"; \
		exit 1; \
	}
	@echo "✅ Python 3 found: $$($(PYTHON) --version)"
	@echo ""
	@echo "Checking for Homebrew..."
	@if ! command -v brew >/dev/null 2>&1; then \
		echo "❌ Homebrew not found. Please install Homebrew first:"; \
		echo "   /bin/bash -c \"\$$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""; \
		echo "   Then run 'make setup' again."; \
		exit 1; \
	fi
	@echo "✅ Homebrew found"
	@echo ""
	@echo "Checking for Tesseract OCR..."
	@if ! command -v tesseract >/dev/null 2>&1; then \
		echo "⚠️  Tesseract OCR not found. Installing..."; \
		brew install tesseract; \
		echo "✅ Tesseract installed successfully!"; \
	else \
		echo "✅ Tesseract found: $$(tesseract --version | head -n1)"; \
	fi
	@echo ""
	@echo "Checking for Python Tkinter (for Finder dialog)..."
	@if ! $(PYTHON) -c "import tkinter" 2>/dev/null; then \
		echo "⚠️  Python Tkinter not found. Installing python-tk..."; \
		brew install python-tk@3.13 || brew install python-tk; \
		echo "✅ Python Tkinter installed successfully!"; \
	else \
		echo "✅ Python Tkinter found"; \
	fi
	@echo ""
	@echo "✅ All dependencies ready!"
	@echo ""

setup: check-deps venv playwright-install
	@echo ""
	@echo "=========================================="
	@echo "✅ SETUP COMPLETE!"
	@echo "=========================================="
	@echo ""
	@echo "Ready to use! Next steps:"
	@echo "  • Run 'make test' to try it out (test mode)"
	@echo "  • Run 'make run' to create real expense reports"
	@echo ""
	@echo "The app will prompt you for LLM API key on first run."
	@echo ""
	@printf '\a'  # Beep!

run:
	@if [ ! -d "$(VENV)" ]; then \
		echo "❌ Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	$(VENV_PYTHON) main.py

run-f:
	@if [ ! -d "$(VENV)" ]; then \
		echo "❌ Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	$(VENV_PYTHON) main.py --use-default-folder

run-f-debug:
	@if [ ! -d "$(VENV)" ]; then \
		echo "❌ Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	$(VENV_PYTHON) main.py --use-default-folder --dump-html

test:
	@if [ ! -d "$(VENV)" ]; then \
		echo "❌ Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	$(VENV_PYTHON) main.py --test

run-verbose:
	@if [ ! -d "$(VENV)" ]; then \
		echo "❌ Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	$(VENV_PYTHON) main.py --verbose

test-reset:
	@if [ ! -d "$(VENV)" ]; then \
		echo "❌ Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	$(VENV_PYTHON) main.py --test --reset-llm

clean:
	@echo "Cleaning up..."
	rm -rf $(VENV)
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -f expense_helper.log
	@echo "✅ Cleaned!"

dist:
	@echo "Creating distribution package..."
	@mkdir -p dist
	@tar -czf dist/expense-helper-$$(date +%Y%m%d).tar.gz \
		--exclude='.venv' \
		--exclude='__pycache__' \
		--exclude='*.pyc' \
		--exclude='.git' \
		--exclude='dist' \
		--exclude='expense_helper.log' \
		--exclude='*.egg-info' \
		.
	@echo "✅ Distribution package created in dist/"
	@ls -lh dist/

