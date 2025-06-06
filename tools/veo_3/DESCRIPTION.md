# Replicate VEO 3 Video Generator

**File:** `veo-3-replicate-video-gen.py`

**Description:**
Generates videos using Replicate's VEO 3 API based on text prompts.

**Main Functions:**
- `generate_video(prompt: str, ...) -> str`: Generates a video using a text prompt.
- `check_prediction_status(prediction_id: str, ...) -> str`: Checks the status of a video generation prediction.
- `cancel_prediction(prediction_id: str, ...) -> str`: Cancels a running prediction.

**Valves:**
- `REPLICATE_API_TOKEN` (str): Replicate API token for accessing VEO 3 API.
- `BASE_URL` (str): Base URL for the Replicate API.
- `MODEL_PATH` (str): Path to the VEO 3 model on Replicate.

**How it works:**
- Validates input parameters and API token.
- Initiates video generation and polls for completion.
- Provides video URLs in a user-friendly format, using a proxy if configured.
- Handles API errors and provides user-friendly error messages.
