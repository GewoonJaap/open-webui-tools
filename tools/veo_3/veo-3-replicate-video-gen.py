"""
title: Replicate VEO 3 Video Generator
author: GardenSnakes
description: A tool that generates videos using Replicate's VEO 3 API based on text prompts.
requirements: requests
version: 0.2.0
author: https://github.com/GewoonJaap/open-webui-tools/
license: MIT
"""

import unittest
import asyncio
import re
from typing import Any, Callable, Optional
import requests
import json
from pydantic import BaseModel, Field


class EventEmitter:
    def __init__(self, event_emitter: Callable[[dict], Any] = None):
        self.event_emitter = event_emitter

    async def progress_update(self, description):
        await self.emit(description)

    async def error_update(self, description):
        await self.emit(description, "error", True)

    async def success_update(self, description):
        await self.emit(description, "success", True)

    async def emit(self, description="Unknown State", status="in_progress", done=False):
        if self.event_emitter:
            await self.event_emitter(
                {
                    "type": "status",
                    "data": {
                        "status": status,
                        "description": description,
                        "done": done,
                    },
                }
            )


class Tools:
    class Valves(BaseModel):
        REPLICATE_API_TOKEN: str = Field(
            default="", description="Replicate API token for accessing VEO 3 API."
        )
        BASE_URL: str = Field(
            default="https://api.replicate.com/v1",
            description="Base URL for the Replicate API.",
        )
        MODEL_PATH: str = Field(
            default="google/veo-3",
            description="Path to the VEO 3 model on Replicate.",
        )
        USE_PROXY: bool = Field(
            default=True,
            description="Enable/disable proxy for video URLs. When enabled, replaces replicate.delivery URLs with ai-asset-proxy.mrproper.dev URLs.",
        )

    def __init__(self):
        self.valves = self.Valves()

    def _replace_replicate_url(self, url: str) -> str:
        """
        Replace Replicate delivery URLs with the proxy URL if proxy is enabled.
        """
        if (
            self.valves.USE_PROXY
            and url
            and url.startswith("https://replicate.delivery/")
        ):
            return url.replace(
                "https://replicate.delivery/",
                "https://ai-asset-proxy.mrproper.dev/api/replicate/",
            )
        return url

    def _format_description_with_prediction_id(
        self, description: str, prediction_id: str = None
    ) -> str:
        """
        Format description to include prediction ID if available.
        """
        if prediction_id:
            return f"{description} [Prediction ID: {prediction_id}]"
        return description

    def _extract_logs_progress(self, logs: str) -> str:
        """
        Extract meaningful progress information from logs.
        """
        if not logs:
            return "Processing..."

        # Check for completion messages
        if "Downloaded video" in logs:
            return "Finalizing video download..."
        elif "Downloading video" in logs:
            return "Video generated successfully, downloading..."
        elif "Generated video in" in logs:
            # Extract generation time if available
            import re

            time_match = re.search(r"Generated video in ([\d.]+) seconds", logs)
            if time_match:
                time_taken = time_match.group(1)
                return f"Video generated in {time_taken} seconds, preparing download..."
            return "Video generation completed, preparing download..."

        # Count occurrences of "Still generating..." to show progress
        still_generating_count = logs.count("Still generating...")
        if still_generating_count > 0:
            return f"Video generation in progress (step {still_generating_count + 1})"
        elif "Starting video generation" in logs:
            return "Starting video generation..."
        elif "Using seed:" in logs:
            return "Initializing generation process..."
        else:
            return "Processing..."

    async def generate_video(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Generates a video using Replicate's VEO 3 API based on a text prompt.
        :param prompt: Text description of the video content you want to generate.
        :param negative_prompt: Text string that describes anything you want to discourage the model from generating.
        :return: A plain text response with the prompt and video URLs.
        """
        emitter = EventEmitter(__event_emitter__)
        prediction_id = None

        try:
            # Validate input parameters
            if not prompt:
                raise Exception("A prompt must be provided")
            # Check if API key is provided
            if not self.valves.REPLICATE_API_TOKEN:
                raise Exception(
                    "No Replicate API token provided. Please set a Replicate API token in tool valves to use this tool."
                )
            # Prepare the API request
            await emitter.progress_update(
                f"Preparing video generation for prompt: '{prompt[:100]}{'...' if len(prompt) > 100 else ''}'"
            )
            # Prepare request data
            input_data = {"prompt": prompt}
            if negative_prompt:
                input_data["negative_prompt"] = negative_prompt
            # Prepare API request
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.valves.REPLICATE_API_TOKEN}",
            }
            url = f"{self.valves.BASE_URL}/models/{self.valves.MODEL_PATH}/predictions"
            # Make the API request
            await emitter.progress_update("Initiating video generation process")
            payload = {"input": input_data}
            response = requests.post(url, headers=headers, json=payload)

            # Check if the request was successful - 200, 201, and 202 are all valid
            if response.status_code not in [200, 201, 202]:
                error_info = response.text
                raise Exception(
                    f"API request failed with status code: {response.status_code}. Details: {error_info}"
                )

            # Parse the response
            response_data = response.json()
            prediction_id = response_data.get("id")

            if not prediction_id:
                raise Exception("Failed to get prediction ID from API response")

            # Handle different response scenarios
            status = response_data.get("status")

            if response.status_code == 202 or status in ["starting", "processing"]:
                # Request accepted, video generation in progress
                await emitter.progress_update(
                    self._format_description_with_prediction_id(
                        f"Video generation request accepted and initiated",
                        prediction_id,
                    )
                )
            elif status == "succeeded":
                # Immediately completed (unlikely but possible)
                await emitter.progress_update(
                    self._format_description_with_prediction_id(
                        "Video generation complete!", prediction_id
                    )
                )
            elif status == "failed":
                error_details = response_data.get("error") or "Unknown error"
                raise Exception(
                    f"Video generation failed: {error_details}. Prediction ID: {prediction_id}"
                )
            else:
                await emitter.progress_update(
                    self._format_description_with_prediction_id(
                        f"Video generation initiated with status: {status}",
                        prediction_id,
                    )
                )

            # If not immediately completed, poll for completion
            if status != "succeeded":
                await emitter.progress_update(
                    self._format_description_with_prediction_id(
                        "Waiting for video generation to complete (this may take 10-15 minutes)",
                        prediction_id,
                    )
                )
                complete = False
                max_retries = (
                    180  # 30 minutes with 10-second intervals (extended for VEO 3)
                )
                retry_count = 0
                last_logs = ""

                while not complete and retry_count < max_retries:
                    check_url = f"{self.valves.BASE_URL}/predictions/{prediction_id}"
                    check_response = requests.get(
                        check_url,
                        headers={
                            "Authorization": f"Bearer {self.valves.REPLICATE_API_TOKEN}"
                        },
                    )

                    if check_response.status_code != 200:
                        raise Exception(
                            f"Failed to check prediction status: {check_response.status_code}. Prediction ID: {prediction_id}"
                        )

                    status_data = check_response.json()
                    status = status_data.get("status")
                    logs = status_data.get("logs", "")

                    if status == "succeeded":
                        complete = True
                        await emitter.progress_update(
                            self._format_description_with_prediction_id(
                                "Video generation complete!", prediction_id
                            )
                        )
                        response_data = status_data
                    elif status == "failed":
                        error_details = status_data.get("error") or "Unknown error"
                        raise Exception(
                            f"Video generation failed: {error_details}. Prediction ID: {prediction_id}"
                        )
                    else:
                        retry_count += 1
                        # Update progress based on logs if they changed
                        if logs and logs != last_logs:
                            progress_info = self._extract_logs_progress(logs)
                            await emitter.progress_update(
                                self._format_description_with_prediction_id(
                                    progress_info, prediction_id
                                )
                            )
                            last_logs = logs
                        else:
                            await emitter.progress_update(
                                self._format_description_with_prediction_id(
                                    f"Video still generating... (check {retry_count}/{max_retries})",
                                    prediction_id,
                                )
                            )
                        await asyncio.sleep(
                            10
                        )  # Wait for 10 seconds before checking again

                if not complete:
                    raise Exception(
                        f"Video generation timed out after 30 minutes. The process may still be running. Check prediction status later. Prediction ID: {prediction_id}"
                    )

            # Process the output
            video_url = response_data.get("output")

            if video_url:
                # Replace Replicate URL with proxy URL if proxy is enabled
                original_url = video_url
                video_url = self._replace_replicate_url(video_url)

                # Send the video URL in a video tag
                await __event_emitter__(
                    {
                        "type": "message",
                        "data": {"content": f"<video>\n{video_url}\n</video>\n\n"},
                    }
                )

                # Create the response text with detailed information
                response_text = f"Video has been generated successfully!"
                response_text += f"\nPrediction ID: {prediction_id}"

                # Add generation time if available
                metrics = response_data.get("metrics", {})
                if "predict_time" in metrics:
                    predict_time = round(metrics["predict_time"], 2)
                    response_text += f"\nGeneration time: {predict_time} seconds"

                proxy_status = "enabled" if self.valves.USE_PROXY else "disabled"
                response_text += f"\nProxy: {proxy_status}"

                if self.valves.USE_PROXY and original_url != video_url:
                    response_text += f"\nOriginal URL: {original_url}"

                await emitter.success_update(
                    self._format_description_with_prediction_id(
                        "Video generation successful! Video is ready to view.",
                        prediction_id,
                    )
                )
                return response_text.strip()
            else:
                error_msg = f"No video URL found in the response. Status: {response_data.get('status')}"
                if prediction_id:
                    error_msg += f" Prediction ID: {prediction_id}"
                raise Exception(error_msg)
        except Exception as e:
            error_message = f"Error: {str(e)}"
            if "401" in str(e) or "403" in str(e):
                error_message += (
                    " (API token issue. Please check your Replicate API token.)"
                )
            if prediction_id and "Prediction ID:" not in error_message:
                error_message += f" Prediction ID: {prediction_id}"
            await emitter.error_update(
                self._format_description_with_prediction_id(
                    error_message, prediction_id
                )
            )
            return error_message

    async def check_prediction_status(
        self,
        prediction_id: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Check the status of a video generation prediction.
        :param prediction_id: The prediction ID returned by the generate_video method.
        :return: A plain text response with the video URL in a <video> tag if the prediction is complete.
        """
        emitter = EventEmitter(__event_emitter__)
        try:
            await emitter.progress_update(
                self._format_description_with_prediction_id(
                    "Checking status for prediction", prediction_id
                )
            )
            # Check if prediction ID is provided
            if not prediction_id or prediction_id == "":
                raise Exception(
                    "Invalid prediction ID: Please provide a valid prediction ID"
                )
            # Check if API token is provided
            if not self.valves.REPLICATE_API_TOKEN:
                raise Exception(
                    f"No Replicate API token provided. Please set a Replicate API token in tool valves to use this tool. Prediction ID: {prediction_id}"
                )
            # Make the API request to check status
            headers = {
                "Authorization": f"Bearer {self.valves.REPLICATE_API_TOKEN}",
                "Content-Type": "application/json",
            }
            url = f"{self.valves.BASE_URL}/predictions/{prediction_id}"
            response = requests.get(url, headers=headers)
            # Check if the request was successful
            if response.status_code != 200:
                error_info = response.text
                raise Exception(
                    f"Status check failed with status code: {response.status_code}. Details: {error_info}. Prediction ID: {prediction_id}"
                )
            # Parse the response
            status_data = response.json()
            status = status_data.get("status")
            logs = status_data.get("logs", "")

            if status == "succeeded":
                await emitter.success_update(
                    self._format_description_with_prediction_id(
                        "Prediction is complete!", prediction_id
                    )
                )
                # Get video URL
                video_url = status_data.get("output")
                original_url = video_url
                # Replace Replicate URL with proxy URL if proxy is enabled
                video_url = self._replace_replicate_url(video_url)

                # Create the response text with video tag
                if video_url:
                    await __event_emitter__(
                        {
                            "type": "message",
                            "data": {"content": f"<video>\n{video_url}\n</video>\n\n"},
                        }
                    )
                    response_text = (
                        f"Video has been generated for prediction: {prediction_id}"
                    )

                    # Add generation time if available
                    metrics = status_data.get("metrics", {})
                    if "predict_time" in metrics:
                        predict_time = round(metrics["predict_time"], 2)
                        response_text += f"\nGeneration time: {predict_time} seconds"

                    proxy_status = "enabled" if self.valves.USE_PROXY else "disabled"
                    response_text += f"\nProxy: {proxy_status}"

                    if self.valves.USE_PROXY and original_url != video_url:
                        response_text += f"\nOriginal URL: {original_url}"

                    return response_text.strip()
                else:
                    return f"Prediction is complete, but no video URL found in the response. Prediction ID: {prediction_id}"
            elif status == "failed":
                error_details = status_data.get("error") or "Unknown error"
                await emitter.error_update(
                    self._format_description_with_prediction_id(
                        f"Prediction failed: {error_details}", prediction_id
                    )
                )
                return f"Error: {error_details}. Prediction ID: {prediction_id}"
            elif status in ["processing", "starting"]:
                progress_info = self._extract_logs_progress(logs)
                await emitter.progress_update(
                    self._format_description_with_prediction_id(
                        progress_info, prediction_id
                    )
                )
                return f"Video generation is still {status}. {progress_info}. Please check again later. Prediction ID: {prediction_id}"
            else:
                await emitter.progress_update(
                    self._format_description_with_prediction_id(
                        f"Prediction status: {status}", prediction_id
                    )
                )
                return f"Video generation is {status}. Please check again later. Prediction ID: {prediction_id}"
        except Exception as e:
            error_message = f"Error: {str(e)}"
            if "401" in str(e) or "403" in str(e):
                error_message += (
                    " (API token issue. Please check your Replicate API token.)"
                )
            if prediction_id and "Prediction ID:" not in error_message:
                error_message += f" Prediction ID: {prediction_id}"
            await emitter.error_update(
                self._format_description_with_prediction_id(
                    error_message, prediction_id
                )
            )
            return error_message

    async def cancel_prediction(
        self,
        prediction_id: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Cancel a running prediction.
        :param prediction_id: The prediction ID to cancel.
        :return: A response indicating whether the cancellation was successful.
        """
        emitter = EventEmitter(__event_emitter__)
        try:
            await emitter.progress_update(
                self._format_description_with_prediction_id(
                    "Cancelling prediction", prediction_id
                )
            )
            # Check if prediction ID is provided
            if not prediction_id or prediction_id == "":
                raise Exception(
                    "Invalid prediction ID: Please provide a valid prediction ID"
                )
            # Check if API token is provided
            if not self.valves.REPLICATE_API_TOKEN:
                raise Exception(
                    f"No Replicate API token provided. Please set a Replicate API token in tool valves to use this tool. Prediction ID: {prediction_id}"
                )
            # Make the API request to cancel prediction
            headers = {
                "Authorization": f"Bearer {self.valves.REPLICATE_API_TOKEN}",
                "Content-Type": "application/json",
            }
            url = f"{self.valves.BASE_URL}/predictions/{prediction_id}/cancel"
            response = requests.post(url, headers=headers)
            # Check if the request was successful
            if response.status_code != 200:
                error_info = response.text
                raise Exception(
                    f"Cancellation failed with status code: {response.status_code}. Details: {error_info}. Prediction ID: {prediction_id}"
                )
            await emitter.success_update(
                self._format_description_with_prediction_id(
                    f"Successfully cancelled prediction", prediction_id
                )
            )
            return f"Successfully cancelled prediction {prediction_id}"
        except Exception as e:
            error_message = f"Error: {str(e)}"
            if prediction_id and "Prediction ID:" not in error_message:
                error_message += f" Prediction ID: {prediction_id}"
            await emitter.error_update(
                self._format_description_with_prediction_id(
                    error_message, prediction_id
                )
            )
            return error_message


class ReplicateVeoToolTest(unittest.IsolatedAsyncioTestCase):
    async def test_generate_video_with_invalid_input(self):
        response = await Tools().generate_video("")
        self.assertTrue("Error" in response)

    async def test_replace_replicate_url_with_proxy_enabled(self):
        tool = Tools()
        tool.valves.USE_PROXY = True
        original_url = "https://replicate.delivery/xezq/iRCY4JYGFbrRCNTLUUVL3bclZk65ZQecj1BgFrrFovnItXaKA/tmpeafl3mlm.mp4"
        expected_url = "https://ai-asset-proxy.mrproper.dev/api/replicate/xezq/iRCY4JYGFbrRCNTLUUVL3bclZk65ZQecj1BgFrrFovnItXaKA/tmpeafl3mlm.mp4"
        self.assertEqual(tool._replace_replicate_url(original_url), expected_url)

    async def test_replace_replicate_url_with_proxy_disabled(self):
        tool = Tools()
        tool.valves.USE_PROXY = False
        original_url = "https://replicate.delivery/xezq/iRCY4JYGFbrRCNTLUUVL3bclZk65ZQecj1BgFrrFovnItXaKA/tmpeafl3mlm.mp4"
        # Should return original URL when proxy is disabled
        self.assertEqual(tool._replace_replicate_url(original_url), original_url)

        # Test with non-replicate URL
        other_url = "https://example.com/video.mp4"
        self.assertEqual(tool._replace_replicate_url(other_url), other_url)

    def test_format_description_with_prediction_id(self):
        tool = Tools()
        description = "Video generation complete"
        prediction_id = "abc123"
        expected = "Video generation complete [Prediction ID: abc123]"
        self.assertEqual(
            tool._format_description_with_prediction_id(description, prediction_id),
            expected,
        )

        # Test without prediction ID
        self.assertEqual(
            tool._format_description_with_prediction_id(description, None), description
        )

    def test_extract_logs_progress(self):
        tool = Tools()

        # Test with complete logs (like the example)
        logs_complete = "Using seed: 954430360\nStarting video generation...\nStill generating...\nStill generating...\nStill generating...\nGenerated video in 139.37 seconds\nDownloading video...\nDownloaded video in 0.12 seconds"
        result_complete = tool._extract_logs_progress(logs_complete)
        self.assertEqual(result_complete, "Finalizing video download...")

        # Test with downloading logs
        logs_downloading = "Using seed: 954430360\nStarting video generation...\nStill generating...\nGenerated video in 139.37 seconds\nDownloading video..."
        result_downloading = tool._extract_logs_progress(logs_downloading)
        self.assertEqual(
            result_downloading, "Video generated successfully, downloading..."
        )

        # Test with generation complete logs
        logs_generated = "Using seed: 954430360\nStarting video generation...\nStill generating...\nGenerated video in 139.37 seconds"
        result_generated = tool._extract_logs_progress(logs_generated)
        self.assertEqual(
            result_generated, "Video generated in 139.37 seconds, preparing download..."
        )

        # Test with "Still generating..." logs
        logs_generating = "Using seed: 954430360\nStarting video generation...\nStill generating...\nStill generating..."
        result_generating = tool._extract_logs_progress(logs_generating)
        self.assertEqual(result_generating, "Video generation in progress (step 3)")


if __name__ == "__main__":
    print("Running tests...")
    unittest.main()
