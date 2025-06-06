# Google Maps Text Search

**File:** `google-maps-tool.py`

**Description:**
Returns place suggestions for a specified query and location using the Google Maps Text Search (New) API.

**Main Function:**
- `get_place_suggestions(query: str, location_bias: str = None, ...) -> str`: Returns place suggestions based on a text query and optional location bias.

**Valves:**
- `CITATION` (bool): Whether to include citations in the response. Default: `True`.
- `GOOGLE_MAPS_API_KEY` (str): Global Google Maps API key for accessing the Places API.

**How it works:**
- Accepts a text query and optional location bias.
- Uses the Google Maps Places API to fetch place suggestions.
- Handles API errors and provides user-friendly error messages, including hints for API key issues.
