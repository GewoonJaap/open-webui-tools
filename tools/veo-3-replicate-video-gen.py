"""
title: Replicate VEO 3 Video Generator
author: GardenSnakes
description: A tool that generates videos using Replicate's VEO 3 API based on text prompts.
requirements: requests
version: 0.1.1
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

    def __init__(self):
        self.valves = self.Valves()

    def _replace_replicate_url(self, url: str) -> str:
        """
        Replace Replicate delivery URLs with the proxy URL.
        """
        if url and url.startswith("https://replicate.delivery/"):
            return url.replace(
                "https://replicate.delivery/",
                "https://ai-asset-proxy.mrproper.dev/api/replicate/",
            )
        return url

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
                f"Preparing video generation for prompt: '{prompt}'"
            )
            # Prepare request data
            input_data = {"prompt": prompt}
            if negative_prompt:
                input_data["negative_prompt"] = negative_prompt
            # Prepare API request
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.valves.REPLICATE_API_TOKEN}",
                "Prefer": "wait",  # This makes the API wait for the result instead of returning immediately
            }
            url = f"{self.valves.BASE_URL}/models/{self.valves.MODEL_PATH}/predictions"
            # Make the API request
            await emitter.progress_update("Initiating video generation process")
            payload = {"input": input_data}
            response = requests.post(url, headers=headers, json=payload)
            # Check if the request was successful
            if response.status_code != 200 and response.status_code != 201:
                error_info = response.text
                raise Exception(
                    f"API request failed with status code: {response.status_code}. Details: {error_info}"
                )
            # Parse the response
            response_data = response.json()
            # Check if the video generation is pending
            if (
                response_data.get("status") == "starting"
                or response_data.get("status") == "processing"
            ):
                prediction_id = response_data.get("id")
                if not prediction_id:
                    raise Exception("Failed to get prediction ID from API response")
                await emitter.progress_update(
                    f"Video generation initiated. Prediction ID: {prediction_id}"
                )
                # Poll for completion
                await emitter.progress_update(
                    "Waiting for video generation to complete (this may take several minutes)"
                )
                complete = False
                max_retries = 60  # Maximum number of retries
                retry_count = 0
                while not complete and retry_count < max_retries:
                    check_url = f"{self.valves.BASE_URL}/predictions/{prediction_id}"
                    check_response = requests.get(check_url, headers=headers)
                    if check_response.status_code != 200:
                        raise Exception(
                            f"Failed to check prediction status: {check_response.status_code}"
                        )
                    status_data = check_response.json()
                    status = status_data.get("status")
                    if status == "succeeded":
                        complete = True
                        await emitter.progress_update("Video generation complete!")
                        response_data = status_data
                    elif status == "failed":
                        error_details = status_data.get("error") or "Unknown error"
                        raise Exception(f"Video generation failed: {error_details}")
                    else:
                        retry_count += 1
                        await emitter.progress_update(
                            f"Video still generating... (check {retry_count}/{max_retries})"
                        )
                        await asyncio.sleep(
                            5
                        )  # Wait for 5 seconds before checking again
                if not complete:
                    raise Exception(
                        "Video generation timed out. The process may still be running. Check the prediction ID later."
                    )
            # Process the output
            video_url = None
            if response_data.get("output"):
                video_url = response_data["output"]
                # Replace Replicate URL with proxy URL
                video_url = self._replace_replicate_url(video_url)

            if video_url:
                # Send the video URL in a video tag
                await __event_emitter__(
                    {
                        "type": "message",
                        "data": {"content": f"<video>\n{video_url}\n</video>\n\n"},
                    }
                )
                # Create the response text with prompt and video information
                response_text = f"Video has been generated with prompt: {prompt}"
                await emitter.success_update(
                    "Video generation successful! Video is ready to view."
                )
                return response_text.strip()
            else:
                raise Exception(f"No video URL found in the response. {response_data}")
        except Exception as e:
            error_message = f"Error: {str(e)}"
            if "401" in str(e) or "403" in str(e):
                error_message += (
                    " (API token issue. Please check your Replicate API token.)"
                )
            await emitter.error_update(error_message)
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
                f"Checking status for prediction: {prediction_id}"
            )
            # Check if prediction ID is provided
            if not prediction_id or prediction_id == "":
                raise Exception(
                    "Invalid prediction ID: Please provide a valid prediction ID"
                )
            # Check if API token is provided
            if not self.valves.REPLICATE_API_TOKEN:
                raise Exception(
                    "No Replicate API token provided. Please set a Replicate API token in tool valves to use this tool."
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
                    f"Status check failed with status code: {response.status_code}. Details: {error_info}"
                )
            # Parse the response
            status_data = response.json()
            status = status_data.get("status")
            if status == "succeeded":
                await emitter.success_update("Prediction is complete!")
                # Get video URL
                video_url = status_data.get("output")
                # Replace Replicate URL with proxy URL
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
                    return response_text.strip()
                else:
                    return (
                        "Prediction is complete, but no video URL found in the response"
                    )
            elif status == "failed":
                error_details = status_data.get("error") or "Unknown error"
                await emitter.error_update(f"Prediction failed: {error_details}")
                return f"Error: {error_details}"
            else:
                await emitter.progress_update(f"Prediction status: {status}")
                return f"Video generation is still {status}. Please check again later."
        except Exception as e:
            error_message = f"Error: {str(e)}"
            if "401" in str(e) or "403" in str(e):
                error_message += (
                    " (API token issue. Please check your Replicate API token.)"
                )
            await emitter.error_update(error_message)
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
            await emitter.progress_update(f"Cancelling prediction: {prediction_id}")
            # Check if prediction ID is provided
            if not prediction_id or prediction_id == "":
                raise Exception(
                    "Invalid prediction ID: Please provide a valid prediction ID"
                )
            # Check if API token is provided
            if not self.valves.REPLICATE_API_TOKEN:
                raise Exception(
                    "No Replicate API token provided. Please set a Replicate API token in tool valves to use this tool."
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
                    f"Cancellation failed with status code: {response.status_code}. Details: {error_info}"
                )
            await emitter.success_update(
                f"Successfully cancelled prediction {prediction_id}"
            )
            return f"Successfully cancelled prediction {prediction_id}"
        except Exception as e:
            error_message = f"Error: {str(e)}"
            await emitter.error_update(error_message)
            return error_message


class ReplicateVeoToolTest(unittest.IsolatedAsyncioTestCase):
    async def test_generate_video_with_invalid_input(self):
        response = await Tools().generate_video("")
        self.assertTrue("Error" in response)

    async def test_replace_replicate_url(self):
        tool = Tools()
        original_url = "https://replicate.delivery/pbxt/JzGrWGQ3tVEQoYQkOKOuvmYfZsGn85RIBhb3OKqtVdRZjnvhA/output.mp4"
        expected_url = "https://ai-asset-proxy.mrproper.dev/api/replicate/pbxt/JzGrWGQ3tVEQoYQkOKOuvmYfZsGn85RIBhb3OKqtVdRZjnvhA/output.mp4"
        self.assertEqual(tool._replace_replicate_url(original_url), expected_url)

        # Test with non-replicate URL
        other_url = "https://example.com/video.mp4"
        self.assertEqual(tool._replace_replicate_url(other_url), other_url)


if __name__ == "__main__":
    print("Running tests...")
    unittest.main()
