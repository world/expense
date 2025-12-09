"""
Airfare-specific expense field handlers (flight type, class, ticket, cities, etc.).
"""
from playwright.sync_api import Page
from browser_dropdowns import select_dropdown_by_value_with_retry


def fill_airfare_fields(
    page: Page,
    flight_type: str = "",
    flight_class: str = "",
    ticket_number: str = "",
    departure_city: str = "",
    arrival_city: str = "",
    passenger_name: str = "",
    agency: str = "",
    logger=None
):
    """
    Fill all flight-specific fields for Travel-Airfare expense type.
    
    Args:
        page: Playwright page
        flight_type: "Domestic" or "International"
        flight_class: "Business", "Coach", etc.
        ticket_number: Ticket/confirmation number
        departure_city: Origin city
        arrival_city: Destination city
        passenger_name: Passenger full name
        agency: Travel agency name
        logger: Optional logger
    """
    if logger:
        logger.info("✈️  Airfare type - filling flight details...")
        logger.info(f"  Flight Type: '{flight_type}', Flight Class: '{flight_class}'")
    
    # Flight Type (Domestic/International)
    if flight_type:
        try:
            flight_type_selector = "select[id*='TravelType'], select[id*='FlightType'], select[id*='flightType']"
            
            if logger:
                logger.info(f"  Looking for Flight Type field...")
            
            # Map label to value
            ft_lower = flight_type.lower()
            ft_value = None
            if "domestic" in ft_lower:
                ft_value = "1"
            elif "international" in ft_lower:
                ft_value = "2"
            
            if logger:
                logger.info(f"  Selecting Flight Type value '{ft_value}' for '{flight_type}'")
            
            if ft_value:
                success = select_dropdown_by_value_with_retry(
                    page, flight_type_selector, ft_value, flight_type, logger
                )
                if not success and logger:
                    logger.warning(f"Could not fill Flight Type '{flight_type}'")
            
        except Exception as e:
            if logger:
                logger.warning(f"Could not fill Flight Type '{flight_type}': {e}")
    
    # Flight Class (Business/Coach)
    if flight_class:
        try:
            flight_class_selector = "select[id*='TicketClassCode'], select[id*='FlightClass'], select[id*='flightClass'], select[id*='ClassOfService']"
            
            if logger:
                logger.info(f"  Looking for Flight Class field...")
            
            # Map label to value
            fc_lower = flight_class.lower()
            fc_value = None
            if "first" in fc_lower:
                fc_value = "1"
            elif "business" in fc_lower:
                fc_value = "2"
            elif "coach" in fc_lower or "economy" in fc_lower:
                fc_value = "3"
            
            if logger:
                logger.info(f"  Selecting Flight Class value '{fc_value}' for '{flight_class}'")
            
            if fc_value:
                success = select_dropdown_by_value_with_retry(
                    page, flight_class_selector, fc_value, flight_class, logger
                )
                if not success and logger:
                    logger.warning(f"Could not fill Flight Class '{flight_class}'")
            
        except Exception as e:
            if logger:
                logger.warning(f"Could not fill Flight Class '{flight_class}': {e}")
    
    # Ticket Number
    if ticket_number:
        try:
            ticket_selector = "input[id*='TicketNumber'], input[id*='ticketNumber'], input[id*='ConfirmationNumber']"
            ticket_loc = page.locator(ticket_selector).first
            ticket_loc.wait_for(state="visible", timeout=500)
            ticket_loc.fill(ticket_number)
            if logger:
                logger.info(f"✅ Set Ticket Number: {ticket_number}")
        except Exception as e:
            if logger:
                logger.warning(f"Could not fill Ticket Number: {e}")
    
    # Departure City
    if departure_city:
        try:
            departure_selector = "input[id*='DestinationFrom'], input[aria-label='Departure City'], input[id*='DepartureCity'], input[id*='departureCity'], input[id*='OriginCity']"
            departure_loc = page.locator(departure_selector).first
            departure_loc.wait_for(state="visible", timeout=500)
            departure_loc.fill(departure_city)
            if logger:
                logger.info(f"✅ Set Departure City: {departure_city}")
        except Exception as e:
            if logger:
                logger.warning(f"Could not fill Departure City: {e}")
    
    # Arrival City
    if arrival_city:
        try:
            arrival_selector = "input[id*='DestinationTo'], input[aria-label='Arrival City'], input[id*='ArrivalCity'], input[id*='arrivalCity'], input[id*='DestinationCity']"
            arrival_loc = page.locator(arrival_selector).first
            arrival_loc.wait_for(state="visible", timeout=500)
            arrival_loc.fill(arrival_city)
            if logger:
                logger.info(f"✅ Set Arrival City: {arrival_city}")
        except Exception as e:
            if logger:
                logger.warning(f"Could not fill Arrival City: {e}")
    
    # Passenger Name
    if passenger_name:
        try:
            passenger_selector = "input[id*='PassengerName'], input[id*='passengerName'], input[id*='Traveler']"
            passenger_loc = page.locator(passenger_selector).first
            passenger_loc.wait_for(state="visible", timeout=500)
            passenger_loc.fill(passenger_name)
            if logger:
                logger.info(f"✅ Set Passenger Name: {passenger_name}")
        except Exception as e:
            if logger:
                logger.warning(f"Could not fill Passenger Name: {e}")
    
    # Agency (combobox input)
    if agency:
        try:
            agency_selector = "input[id*='agencyTravelAirfare'], input[role='combobox'][id*='agency'], input[id*='Agency']"
            agency_loc = page.locator(agency_selector).first
            agency_loc.wait_for(state="visible", timeout=500)
            agency_loc.fill(agency)
            if logger:
                logger.info(f"✅ Set Agency: {agency}")
        except Exception as e:
            if logger:
                logger.warning(f"Could not fill Agency: {e}")

