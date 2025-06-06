# Flight Data Provider

**File:** `flight_tracker.py`

**Description:**
Fetches flight data for a specified flight number using [flight-status.com](https://flight-status.com) via the Jina API.

**Main Function:**
- `get_flight_data(flight_number: str, ...) -> str`: Returns detailed information about a specific flight.

**Valves:**
- `CITATION` (bool): Whether to include citations in the response. Default: `True`.
- `GLOBAL_JINA_API_KEY` (str): Global Jina API key for accessing the flight data API.

**User Valves:**
- `JINA_API_KEY` (str): Optional user-specific Jina API key. If provided, overrides the global key.

**How it works:**
- Validates the flight number.
- Uses the Jina API to fetch and parse flight data from flight-status.com.
- Handles API errors and provides user-friendly error messages, including hints for API key issues.
