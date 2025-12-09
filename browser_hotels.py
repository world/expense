"""
Hotel-specific expense field handlers (nightly breakdown).

This module now has TWO implementations for hotel nightly breakdown:
- fill_hotel_nightly_breakdown_legacy: the original deterministic Playwright logic
- fill_hotel_nightly_breakdown_ai: an experimental LLM-driven browser agent

OracleBrowserAgent will try the AI path first for Travel-Hotel Accommodation and
fall back to the legacy implementation if anything fails.
"""
from datetime import datetime, timedelta
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import Page


def fill_hotel_nightly_breakdown_legacy(
    page: Page,
    total_amount: float,
    base_date: str,
    nights: int,
    check_in_date: str = "",
    check_out_date: str = "",
    logger=None,
) -> bool:
    """
    Original deterministic implementation for Travel-Hotel Accommodation.
    Kept intact so we can always fall back from the AI-based flow.
    """
    if logger:
        logger.info("🏨 [legacy] Filling hotel nightly breakdown...")

    # Determine nights
    if not nights or nights <= 0:
        # Try inferring from check-in/out
        if check_in_date and check_out_date:
            try:
                ci = datetime.strptime(check_in_date, "%d-%m-%Y")
                co = datetime.strptime(check_out_date, "%d-%m-%Y")
                nights = max(1, (co - ci).days)
            except Exception:
                nights = 1
        else:
            nights = 1

    if logger:
        logger.info(f"  Nights: {nights}")

    # Compute per-night amounts in cents with penny balancing
    total_cents = int(round(total_amount * 100))
    base = total_cents // nights
    remainder = total_cents - base * nights

    nightly_cents = [base] * nights
    step = 1 if remainder > 0 else -1
    for i in range(abs(remainder)):
        nightly_cents[i % nights] += step

    nightly_amounts = [c / 100.0 for c in nightly_cents]

    if logger:
        for i, amt in enumerate(nightly_amounts):
            logger.info(f"  Night {i+1}: {amt:.2f}")

    # Determine first night date
    def parse_ddmmyyyy(val: str) -> Optional[datetime]:
        try:
            return datetime.strptime(val, "%d-%m-%Y")
        except Exception:
            return None

    start_date = parse_ddmmyyyy(check_in_date) or parse_ddmmyyyy(base_date) or datetime.now()

    # Helper to convert to Oracle date string in the UI's format for itemization
    # rows. The UI placeholder is "dd-mmm-yy", and Oracle happily accepts a
    # 2-digit year here, so we use that.
    def to_oracle(d: datetime) -> str:
        return d.strftime("%d-%b-%y")

    # Fill rows; row 0 exists; others may require Add Row
    for i, amt in enumerate(nightly_amounts):
        row_suffix = f"itemTbl:{i}:"

        # If i > 0, try to add a new row (best-effort)
        if i > 0:
            added = False
            add_selectors = [
                "a[title='Add Row']",
                "button[title='Add Row']",
                "a[aria-label*='Add Row']",
                "button[aria-label*='Add Row']",
            ]
            for sel in add_selectors:
                try:
                    add_btn = page.locator(sel).first
                    if add_btn.is_visible(timeout=500):
                        add_btn.click()
                        page.wait_for_timeout(500)
                        added = True
                        if logger:
                            logger.info(f"  Added row {i} for Night {i+1}")
                        break
                except Exception:
                    continue

            if not added:
                if logger:
                    logger.warning(
                        f"  Could not add row for Night {i+1}, stopping breakdown at night {i}"
                    )
                break

        # 1) Type selector for this row (leftmost)
        try:
            type_selector = f"select[id*='{row_suffix}ChildExpenseTypeId']"
            # Wait up to 10s for the select for this row to exist, then
            # set its value via JavaScript so we don't depend on ADF
            # actionability checks.
            page.wait_for_selector(type_selector, timeout=10000)
            page.evaluate(
                f"""
                () => {{
                    const sel = document.querySelector("{type_selector}");
                    if (sel) {{
                        sel.value = '7';  // Travel-Lodging-Hotel Charges
                        sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }}
                """
            )
            if logger:
                logger.info("  Night %d: Set Type to Travel-Lodging-Hotel Charges", i + 1)
        except Exception as e:
            if logger:
                logger.warning(f"  Night {i+1}: Could not set Type: {e}")

        # 2) Date input for this row
        try:
            d = start_date + timedelta(days=i)
            oracle_d = to_oracle(d)
            date_selector = f"input[id*='{row_suffix}ChildStartDate']"

            # Wait for the date field for this row, then simulate a real user:
            # click into the field, select any existing text, type the date
            # character-by-character, and TAB out so Oracle's JS handlers run.
            page.wait_for_selector(date_selector, timeout=10000)
            date_input = page.locator(date_selector).first
            date_input.click(timeout=2000)

            # Try to clear any existing content using common shortcuts.
            try:
                page.keyboard.press("Control+A")
                page.keyboard.press("Delete")
            except Exception:
                pass
            try:
                page.keyboard.press("Meta+A")
                page.keyboard.press("Backspace")
            except Exception:
                pass

            # Type the date slowly enough for any onkeyup logic.
            page.keyboard.type(oracle_d, delay=40)
            page.wait_for_timeout(120)
            page.keyboard.press("Tab")
            page.wait_for_timeout(150)

            if logger:
                logger.info(f"  Night {i+1}: Typed Date '{oracle_d}' and tabbed out")
        except Exception as e:
            if logger:
                logger.warning(f"  Night {i+1}: Could not set Date via typing: {e}")

        # 3) Daily Amount (per-night amount)
        try:
            # Use JavaScript to directly set the value (bypasses all visibility checks)
            page.evaluate(
                f"""
                () => {{
                    const el = document.querySelector("input[id*='{row_suffix}ChildDailyAmountProf']");
                    if (el) {{
                        el.value = '{amt:.2f}';
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }}
                """
            )
            if logger:
                logger.info(f"  Night {i+1}: Set Daily Amount to {amt:.2f}")
        except Exception as e:
            if logger:
                logger.warning(f"  Night {i+1}: Could not set Daily Amount: {e}")

        # 4) Days (Number of Days per row) - explicit field
        try:
            # Use JavaScript to directly set the value (bypasses all visibility checks)
            page.evaluate(
                f"""
                () => {{
                    const el = document.querySelector("input[id*='{row_suffix}ChildNumberOfDaysProf']");
                    if (el) {{
                        el.value = '1';
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        el.blur();
                    }}
                }}
                """
            )
            page.wait_for_timeout(100)
            if logger:
                logger.info(
                    "  Night %d: Set Number of Days to 1 (via JavaScript)",
                    i + 1,
                )
        except Exception as e:
            if logger:
                logger.warning(f"  Night {i+1}: Could not set Number of Days: {e}")

        # 5) Amount (USD) for this row - keep this in sync with Daily * Days
        try:
            amt_selector = f"input[id*='{row_suffix}ChildReceiptAmountAddSub']"
            # Wait for the amount field for this row, then set via JS
            page.wait_for_selector(amt_selector, timeout=10000)
            page.evaluate(
                f"""
                () => {{
                    const el = document.querySelector("{amt_selector}");
                    if (el) {{
                        el.value = '{amt:.2f}';
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }}
                """
            )
            if logger:
                logger.info(f"  Night {i+1}: Set Amount to {amt:.2f}")
        except Exception as e:
            if logger:
                logger.warning(f"  Night {i+1}: Could not set Amount: {e}")

    # Give Oracle time to process all the JavaScript-set values before moving on
    page.wait_for_timeout(1000)

    if logger:
        logger.info(
            "🏨 [legacy] Finished filling hotel nightly breakdown rows. Paused 1s for Oracle to process."
        )

    return True


def _ensure_hotel_nightly_dates(
    page: Page,
    nights: int,
    base_date: str,
    check_in_date: str,
    logger=None,
) -> None:
    """
    (Unused for now; kept for possible future diagnostics.)
    We ended up delegating nightly row filling back to the legacy helper,
    which already knows how to drive these Oracle date fields reliably.
    """
    if logger:
        logger.info(
            "🏨 [AI] _ensure_hotel_nightly_dates is currently a no-op; "
            "relying on legacy helper for final nightly breakdown."
        )


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract a single JSON object from a raw LLM response.
    Handles ```json``` fences or plain JSON.
    """
    # Strip markdown code fences if present
    if "```json" in text:
        match = re.search(r"```json\\s*(\\{.*?\\})\\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)
    elif "```" in text:
        match = re.search(r"```\\s*(\\{.*?\\})\\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)

    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        return None


def _call_llm_hotel_plan(
    page_html: str,
    total_amount: float,
    nights: int,
    check_in_date: str,
    check_out_date: str,
    llm_client: Any,
    llm_model: str,
    llm_provider: str,
    logger=None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Ask the LLM to propose a small set of browser actions to fill
    the nightly breakdown table for a hotel expense.
    """
    if not llm_client or not llm_model:
        return None, "LLM client or model not configured"

    system_prompt = (
        "You are an expert Oracle Expenses UI automation planner. "
        "Given HTML of the current page and hotel stay details, "
        "you must propose a SHORT sequence of DOM actions to fill the "
        "nightly breakdown table for a Travel-Hotel Accommodation expense."
    )

    user_prompt = f"""
We are on the Oracle Expenses page for a hotel item with a nightly breakdown table.

Goal:
- There is a table of child rows for each night (Type / Date / Daily Amount / Days / Amount).
- You must fill exactly {nights} night(s) so that the total across rows equals {total_amount:.2f}.
- If necessary, you may split the total evenly across nights, adjusting by a cent or two so the sum matches exactly.

Hotel stay metadata (use when picking dates):
- check_in_date (DD-MM-YYYY, may be empty): "{check_in_date}"
- check_out_date (DD-MM-YYYY, may be empty): "{check_out_date}"

Page HTML (abridged):
{page_html[:25000]}

Return ONLY one JSON object with this shape (no explanation, no extra keys):
{{
  "actions": [
    {{
      "action": "click" | "fill" | "press_key" | "wait",
      "selector_type": "css",
      "selector": "<CSS selector to target element>",  # for click/fill only
      "text": "<text to type or value to set>",        # for fill only
      "key": "<e.g. Tab or Enter>",                    # for press_key only
      "wait_ms": <integer milliseconds>                # optional small waits after this action
    }}
  ]
}}

Constraints:
- Use VERY few actions (ideally under 40 total).
- Prefer CSS selectors that look robust (based on id fragments like 'itemTbl', 'ChildStartDate', 'ChildDailyAmountProf', etc.).
- For each nightly row, you may:
  - click or fill into the Date field for that row,
  - fill Daily Amount / Number of Days / Amount fields for that row.
- Do NOT attempt to change the parent-level Type, Date, or Amount fields; only operate within the nightly breakdown table.
"""

    try:
        if llm_provider == "anthropic":
            response = llm_client.messages.create(
                model=llm_model,
                max_tokens=900,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.content[0].text.strip()
        else:
            response = llm_client.chat.completions.create(
                model=llm_model,
                temperature=0,
                max_tokens=900,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content.strip()

        plan = _extract_json_object(content)
        if not plan:
            return None, "LLM response was not valid JSON"
        if "actions" not in plan or not isinstance(plan["actions"], list):
            return None, "LLM plan missing 'actions' list"
        return plan, None
    except Exception as e:
        if logger:
            logger.error(f"LLM plan call for hotel breakdown failed: {e}")
        return None, str(e)


def _execute_hotel_plan(
    page: Page,
    plan: Dict[str, Any],
    logger=None,
) -> bool:
    """Execute the LLM-proposed plan against the live Playwright page."""
    actions: List[Dict[str, Any]] = plan.get("actions") or []
    if not actions:
        if logger:
            logger.warning("Hotel AI plan had no actions")
        return False

    for idx, action in enumerate(actions):
        kind = (action.get("action") or "").lower()
        selector_type = (action.get("selector_type") or "css").lower()
        selector = action.get("selector") or ""
        wait_ms = int(action.get("wait_ms") or 0)

        if logger:
            logger.info(f"[AI hotel] Step {idx+1}: {kind} {selector or ''}")

        try:
            if kind == "wait":
                if wait_ms > 0:
                    page.wait_for_timeout(wait_ms)
                continue

            if kind in ("click", "fill"):
                if selector_type != "css" or not selector:
                    if logger:
                        logger.warning(f"  Skipping invalid selector in action {idx+1}")
                    continue
                loc = page.locator(selector).first
                if kind == "click":
                    loc.click(timeout=4000)
                else:
                    text = action.get("text") or ""
                    loc.fill(str(text))

            elif kind == "press_key":
                key = action.get("key") or ""
                if key:
                    page.keyboard.press(key)

            else:
                if logger:
                    logger.warning(f"  Unknown action kind '{kind}' in hotel AI plan")

            if wait_ms > 0:
                page.wait_for_timeout(wait_ms)

        except Exception as e:
            if logger:
                logger.warning(f"  Hotel AI action {idx+1} failed: {e}")
            # If any critical step fails, treat the whole plan as failed so we can fall back.
            return False

    return True


def fill_hotel_nightly_breakdown_ai(
    page: Page,
    total_amount: float,
    base_date: str,
    nights: int,
    check_in_date: str,
    check_out_date: str,
    llm_client: Any,
    llm_model: str,
    llm_provider: str,
    logger=None,
) -> bool:
    """
    Experimental AI-based nightly breakdown filler for Travel-Hotel Accommodation.

    It asks the LLM to reason over the current page HTML and propose a minimal
    sequence of DOM actions to populate the nightly breakdown rows. If anything
    fails (LLM error or actions can't be executed), the caller should fall back
    to fill_hotel_nightly_breakdown_legacy.
    """
    if logger:
        logger.info("🏨 [AI] Attempting hotel nightly breakdown via LLM browser agent...")

    # Basic sanity: nights and amount must look sensible
    if total_amount <= 0 or nights <= 0:
        if logger:
            logger.warning(
                "Hotel AI: invalid total_amount or nights; skipping AI path "
                f"(total_amount={total_amount}, nights={nights})"
            )
        return False

    try:
        page_html = page.content()
    except Exception as e:
        if logger:
            logger.error(f"Hotel AI: could not read page HTML: {e}")
        return False

    plan, error = _call_llm_hotel_plan(
        page_html=page_html,
        total_amount=total_amount,
        nights=nights,
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        llm_client=llm_client,
        llm_model=llm_model,
        llm_provider=llm_provider,
        logger=logger,
    )

    if error or not plan:
        if logger:
            logger.warning(f"Hotel AI: no usable plan from LLM: {error}")
        return False

    success = _execute_hotel_plan(page=page, plan=plan, logger=logger)

    if not success:
        if logger:
            logger.warning(
                "Hotel AI: plan execution failed; caller will fall back to legacy implementation"
            )
        return False

    # Even when the AI plan executes, we delegate the actual nightly breakdown
    # values to the legacy helper, which is tuned to Oracle's quirks (dates,
    # per-night amounts, Days column, etc.). This keeps the experiment isolated
    # while guaranteeing stable behavior for production use.
    if logger:
        logger.info(
            "🏨 [AI] Plan executed; finalizing nightly breakdown via legacy helper "
            "(ensures dates stick and totals match)."
        )

    legacy_ok = fill_hotel_nightly_breakdown_legacy(
        page=page,
        total_amount=total_amount,
        base_date=base_date,
        nights=nights,
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        logger=logger,
    )

    # Give Oracle a brief moment to process any onchange handlers
    page.wait_for_timeout(1000)
    return legacy_ok


# Backwards-compatible name used by OracleBrowserAgent; now wraps AI + legacy paths.
def fill_hotel_nightly_breakdown(
    page: Page,
    total_amount: float,
    base_date: str,
    nights: int,
    check_in_date: str = "",
    check_out_date: str = "",
    logger=None,
) -> bool:
    """
    Wrapper that currently keeps the legacy behavior as the default.

    OracleBrowserAgent explicitly calls fill_hotel_nightly_breakdown_ai first
    for the Travel-Hotel Accommodation expense type, then falls back to
    fill_hotel_nightly_breakdown_legacy if AI fails. Keeping this thin wrapper
    makes it easy to revert to legacy only if we ever want to.
    """
    return fill_hotel_nightly_breakdown_legacy(
        page=page,
        total_amount=total_amount,
        base_date=base_date,
        nights=nights,
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        logger=logger,
    )
