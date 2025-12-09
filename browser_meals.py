"""
Meals-specific expense field handlers (attendee count and names).
"""
from playwright.sync_api import Page


def fill_meals_attendee_fields(
    page: Page,
    user_full_name: str,
    logger=None
):
    """
    Fill attendee count and names for Meals expense types.
    
    Args:
        page: Playwright page
        user_full_name: User's full name for attendee field
        logger: Optional logger
    """
    if logger:
        logger.info("🍽️  Meals type - filling attendee info...")
    
    # Fill Number of Attendees = 1
    try:
        attendee_count_selector = "input[id*='numberOfAttendees']"
        attendee_loc = page.locator(attendee_count_selector).first
        attendee_loc.wait_for(state="visible", timeout=500)
        attendee_loc.fill("1")
        if logger:
            logger.info("✅ Set Number of Attendees: 1")
    except Exception as e:
        if logger:
            logger.warning(f"Could not fill Number of Attendees: {e}")
    
    # Fill Attendee Names with user's name
    try:
        names_selector = "input[id*='attendeesMeals'], input[id*='attendees']"
        names_loc = page.locator(names_selector).first
        names_loc.wait_for(state="visible", timeout=500)
        names_loc.fill(user_full_name)
        if logger:
            logger.info(f"✅ Set Attendees: {user_full_name}")
    except Exception as e:
        if logger:
            logger.warning(f"Could not fill Attendees: {e}")

