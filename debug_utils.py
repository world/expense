"""
Debug helpers for capturing Oracle page HTML when diagnosing tricky UI issues.

Usage:
    from debug_utils import set_debug_dump_html, maybe_dump_page_html

    # In main.py, after parsing args:
    set_debug_dump_html(args.dump_html)

    # Anywhere in browser code:
    maybe_dump_page_html(page, logger, name="before_save_and_close")
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page

_DEBUG_DUMP_HTML: bool = False


def set_debug_dump_html(enabled: bool) -> None:
    """Globally enable/disable HTML dump helper."""
    global _DEBUG_DUMP_HTML
    _DEBUG_DUMP_HTML = bool(enabled)


def maybe_dump_page_html(page: Page, logger=None, name: str = "page") -> Optional[Path]:
    """
    If debug HTML dumping is enabled, write the current page HTML to a file.
    
    The filename is of the form: debug_{name}_YYYYMMDD-HHMMSS.html
    """
    if not _DEBUG_DUMP_HTML:
        return None
    
    try:
        html = page.content()
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"debug_{name}_{ts}.html"
        dump_path = Path(filename).resolve()
        dump_path.write_text(html, encoding="utf-8")
        
        if logger:
            logger.info(f"🔍 Saved page HTML to {dump_path}")
        
        return dump_path
    except Exception as e:
        if logger:
            logger.warning(f"Failed to dump page HTML for '{name}': {e}")
        return None


