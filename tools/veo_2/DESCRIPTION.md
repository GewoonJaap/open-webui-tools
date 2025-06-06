# Google Veo Video Generator

**File:** `veo-video-gen.py`

**Description:**
Generates videos using Google's Veo API based on text prompts or images.

**Main Functions:**
- `generate_video(prompt: str, ...) -> str`: Generates a video using a text prompt or image.
- `check_video_status(operation_name: str, ...) -> str`: Checks the status of a video generation operation.

**Valves:**
- `GOOGLE_API_KEY` (str): Google API key for accessing the Veo API.
- `BASE_URL` (str): Base URL for the Google Veo API.
- `PROXY_URL` (str): Proxy URL for serving Veo videos.
- `CITATION` (bool): Whether to include citations in the response.

**How it works:**
- Validates input parameters and API key.
- Initiates video generation and polls for completion.
- Provides video URLs in a user-friendly format, using a proxy if configured.
- Handles API errors and provides user-friendly error messages.
