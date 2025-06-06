"""
title: Google Veo Video Generator
author: AI Assistant
description: A tool that generates videos using Google's Veo API based on text prompts.
requirements: requests
version: 0.1.1
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
        GOOGLE_API_KEY: str = Field(
            default="", description="Google API key for accessing the Veo API."
        )
        BASE_URL: str = Field(
            default="https://generativelanguage.googleapis.com/v1beta",
            description="Base URL for the Google Veo API.",
        )
        PROXY_URL: str = Field(
            default="https://ai-asset-proxy.mrproper.dev/api/gemini/veo",
            description="Proxy URL for serving Veo videos.",
        )
        CITATION: bool = Field(
            default=True, description="Whether to include citations in the response."
        )

    def __init__(self):
        self.valves = self.Valves()
        self.citation = self.valves.CITATION

    def _extract_video_id(self, uri: str) -> str:
        """Extract the video ID from a Google Veo video URI."""
        # Format: https://generativelanguage.googleapis.com/v1beta/files/[VIDEO_ID]:download?alt=media
        match = re.search(r"files/([a-zA-Z0-9]+)(?::download)?", uri)
        if match:
            return match.group(1)
        return None

    def _create_proxy_url(self, video_id: str, api_key: str) -> str:
        """Create a proxy URL for the video using the specified format."""
        if not video_id:
            return None
        return f"{self.valves.PROXY_URL}/{video_id}/{api_key}"

    async def generate_video(
        self,
        prompt: str,
        aspect_ratio: str = "16:9",
        negative_prompt: Optional[str] = None,
        person_generation: str = "allow_adult",
        number_of_videos: int = 1,
        duration_seconds: int = 8,
        enhance_prompt: bool = True,
        image: Optional[str] = None,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Generates a video using Google's Veo API based on a text prompt or image.

        :param prompt: Text description of the video content you want to generate. Optional if image is provided.
        :param aspect_ratio: The aspect ratio of the video. Supported values are "16:9" and "9:16". Default is "16:9".
        :param negative_prompt: Text string that describes anything you want to discourage the model from generating.
        :param person_generation: Controls generation of people in videos. Options:
            - "dont_allow": Don't allow the inclusion of people or faces
            - "allow_adult": Generate videos that include adults, but not children
            - "allow_all": Generate videos that include adults and children
        :param number_of_videos: Output videos requested, either 1 or 2.
        :param duration_seconds: Length of each output video in seconds, between 5 and 8.
        :param enhance_prompt: Enable or disable the prompt rewriter. Enabled by default.
        :param image: The image to use as the first frame for the video. Optional if prompt is provided.
        :return: A plain text response with the prompt and video URLs in <video> tags.
        """
        emitter = EventEmitter(__event_emitter__)

        try:
            # Validate input parameters
            if not prompt and not image:
                raise Exception("Either prompt or image must be provided")

            # Check if API key is provided
            if not self.valves.GOOGLE_API_KEY:
                raise Exception(
                    "No Google API key provided. Please set a Google API key in tool valves to use this tool."
                )

            # Validate person_generation parameter
            valid_person_options = ["dont_allow", "allow_adult", "allow_all"]
            if person_generation not in valid_person_options:
                raise Exception(
                    f"Invalid person_generation option: {person_generation}. Must be one of: {', '.join(valid_person_options)}"
                )

            # Validate number_of_videos parameter
            if number_of_videos not in [1, 2]:
                raise Exception(
                    f"Invalid number_of_videos: {number_of_videos}. Must be either 1 or 2."
                )

            # Validate duration_seconds parameter
            if duration_seconds < 5 or duration_seconds > 8:
                raise Exception(
                    f"Invalid duration_seconds: {duration_seconds}. Must be between 5 and 8 seconds."
                )

            # Validate aspect_ratio parameter
            valid_aspect_ratios = ["16:9", "9:16"]
            if aspect_ratio not in valid_aspect_ratios:
                raise Exception(
                    f"Invalid aspect_ratio: {aspect_ratio}. Must be one of: {', '.join(valid_aspect_ratios)}"
                )

            # Prepare the API request
            if prompt:
                await emitter.progress_update(
                    f"Preparing video generation for prompt: '{prompt}'"
                )
            else:
                await emitter.progress_update(
                    "Preparing video generation from image input"
                )

            base_url = self.valves.BASE_URL
            headers = {"Content-Type": "application/json"}

            # Create the instance part of the request
            instance = {}
            if prompt:
                instance["prompt"] = prompt
            if image:
                instance["image"] = image

            # Create the parameters section
            parameters = {
                "aspectRatio": aspect_ratio,
                "personGeneration": person_generation,
                "sampleCount": number_of_videos,
                "durationSeconds": duration_seconds,
            }

            # Add negative prompt if provided
            if negative_prompt:
                parameters["negativePrompt"] = negative_prompt

            # Create the complete request payload
            data = {"instances": [instance], "parameters": parameters}

            # Make the API request to initiate video generation
            await emitter.progress_update("Initiating video generation process")
            url = f"{base_url}/models/veo-2.0-generate-001:predictLongRunning?key={self.valves.GOOGLE_API_KEY}"

            response = requests.post(url, headers=headers, json=data)

            # Check if the request was successful
            if response.status_code != 200:
                error_info = response.text
                raise Exception(
                    f"API request failed with status code: {response.status_code}. Details: {error_info}"
                )

            # Parse the response to get the operation name
            response_data = response.json()
            operation_name = response_data.get("name")

            if not operation_name:
                raise Exception("Failed to get operation name from API response")

            await emitter.progress_update(
                f"Video generation initiated. Operation name: {operation_name}"
            )

            # Poll for completion
            await emitter.progress_update(
                "Waiting for video generation to complete (this may take several minutes)"
            )

            complete = False
            max_retries = 60  # Maximum number of retries
            retry_count = 0

            while not complete and retry_count < max_retries:
                check_url = (
                    f"{base_url}/{operation_name}?key={self.valves.GOOGLE_API_KEY}"
                )
                check_response = requests.get(check_url)

                if check_response.status_code != 200:
                    raise Exception(
                        f"Failed to check operation status: {check_response.status_code}"
                    )

                status_data = check_response.json()
                is_done = status_data.get("done", False)

                if is_done:
                    complete = True
                    await emitter.progress_update("Video generation complete!")

                    # Check for errors
                    if "error" in status_data:
                        error_details = status_data.get("error", {})
                        error_message = error_details.get("message", "Unknown error")
                        raise Exception(f"Video generation failed: {error_message}")

                    # Format the response with video URLs in <video> tags using the proxy
                    video_urls = []
                    if (
                        "response" in status_data
                        and "generateVideoResponse" in status_data["response"]
                    ):
                        gen_response = status_data["response"]["generateVideoResponse"]
                        if "generatedSamples" in gen_response:
                            samples = gen_response["generatedSamples"]
                            for sample in samples:
                                if "video" in sample and "uri" in sample["video"]:
                                    uri = sample["video"]["uri"]
                                    # Extract video ID and create proxy URL
                                    video_id = self._extract_video_id(uri)
                                    if video_id:
                                        proxy_url = self._create_proxy_url(
                                            video_id, self.valves.GOOGLE_API_KEY
                                        )
                                        await __event_emitter__(
                                            {
                                                "type": "message",
                                                "data": {
                                                    "content": f"<video>\n{proxy_url}\n</video>\n\n"
                                                },
                                            }
                                        )
                                        video_urls.append(proxy_url)

                    # Create the response text with prompt and video tags
                    if video_urls:
                        # Start with LLM instructions and prompt announcement
                        response_text = (
                            f"Video has been generated with prompt: {prompt}"
                        )

                        await emitter.success_update(
                            "Video generation successful! Videos are ready to view."
                        )
                        return response_text.strip()
                    else:
                        raise Exception(
                            f"No video URLs found in the response. {status_data}"
                        )
                else:
                    retry_count += 1
                    await emitter.progress_update(
                        f"Video still generating... (check {retry_count}/{max_retries})"
                    )
                    await asyncio.sleep(5)  # Wait for 5 seconds before checking again

            if not complete:
                raise Exception(
                    "Video generation timed out. The process may still be running. Check the operation URL later."
                )

        except Exception as e:
            error_message = f"Error: {str(e)}"
            if "401" in str(e) or "403" in str(e):
                error_message += " (API key issue. Please check your Google API key.)"
            await emitter.error_update(error_message)
            return error_message

    async def check_video_status(
        self,
        operation_name: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Check the status of a video generation operation.

        :param operation_name: The operation name returned by the generate_video method.
        :return: A plain text response with the video URLs in <video> tags if the operation is complete.
        """
        emitter = EventEmitter(__event_emitter__)

        try:
            await emitter.progress_update(
                f"Checking status for operation: {operation_name}"
            )

            # Check if operation name is provided
            if not operation_name or operation_name == "":
                raise Exception(
                    "Invalid operation name: Please provide a valid operation name"
                )

            # Check if API key is provided
            if not self.valves.GOOGLE_API_KEY:
                raise Exception(
                    "No Google API key provided. Please set a Google API key in tool valves to use this tool."
                )

            # Make the API request to check status
            base_url = self.valves.BASE_URL
            check_url = f"{base_url}/{operation_name}?key={self.valves.GOOGLE_API_KEY}"

            response = requests.get(check_url)

            # Check if the request was successful
            if response.status_code != 200:
                error_info = response.text
                raise Exception(
                    f"Status check failed with status code: {response.status_code}. Details: {error_info}"
                )

            # Parse the response to get the status data
            status_data = response.json()
            is_done = status_data.get("done", False)

            if is_done:
                await emitter.success_update("Operation is complete!")
                # Check for errors
                if "error" in status_data:
                    error_details = status_data.get("error", {})
                    error_message = error_details.get("message", "Unknown error")
                    await emitter.error_update(f"Operation failed: {error_message}")
                    return f"Error: {error_message}"

                # Format the response with video URLs in <video> tags using the proxy
                video_urls = []

                if (
                    "response" in status_data
                    and "generateVideoResponse" in status_data["response"]
                ):
                    gen_response = status_data["response"]["generateVideoResponse"]
                    if "generatedSamples" in gen_response:
                        samples = gen_response["generatedSamples"]
                        for sample in samples:
                            if "video" in sample and "uri" in sample["video"]:
                                uri = sample["video"]["uri"]
                                # Extract video ID and create proxy URL
                                video_id = self._extract_video_id(uri)
                                if video_id:
                                    proxy_url = self._create_proxy_url(
                                        video_id, self.valves.GOOGLE_API_KEY
                                    )
                                    video_urls.append(proxy_url)

                # Create the response text with video tags
                if video_urls:
                    # Start with LLM instructions and operation announcement
                    response_text = f"Video has been generated for operation: {operation_name}\n\nReply with the following video tags, no markdown, just plain text output, every tag and content on new line, so no ```text or ```html allowed:\n\n"

                    # Add each video URL in the requested format
                    for url in video_urls:
                        response_text += f"<video>\n{url}\n</video>\n"

                    return response_text.strip()
                else:
                    return (
                        "Operation is complete, but no video URLs found in the response"
                    )
            else:
                await emitter.progress_update("Operation is still in progress")
                return (
                    "Video generation is still in progress. Please check again later."
                )

        except Exception as e:
            error_message = f"Error: {str(e)}"
            if "401" in str(e) or "403" in str(e):
                error_message += " (API key issue. Please check your Google API key.)"
            await emitter.error_update(error_message)
            return error_message


class GoogleVeoToolTest(unittest.IsolatedAsyncioTestCase):
    async def test_extract_video_id(self):
        tool = Tools()
        video_id = tool._extract_video_id(
            "https://generativelanguage.googleapis.com/v1beta/files/u6e5f8rzq8cn:download?alt=media"
        )
        self.assertEqual(video_id, "u6e5f8rzq8cn")

        video_id = tool._extract_video_id(
            "https://generativelanguage.googleapis.com/v1beta/files/pbac2s0cpb7a"
        )
        self.assertEqual(video_id, "pbac2s0cpb7a")

    async def test_generate_video_with_invalid_input(self):
        response = await Tools().generate_video("")
        self.assertTrue("Error" in response)


if __name__ == "__main__":
    print("Running tests...")
    unittest.main()
