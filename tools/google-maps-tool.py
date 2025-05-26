"""
title: Google Maps Text Search
author: YourName
author_url: github.com/GewoonJaap/open-webui-tools
description: A tool that returns place suggestions for a specified query and location using the Google Maps Text Search (New) API.
requirements: requests
version: 0.0.1
license: MIT
"""

from typing import Any, Callable
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
        CITATION: bool = Field(default="True", description="True or false for citation")
        GOOGLE_MAPS_API_KEY: str = Field(
            default="",
            description="Global Google Maps API key for accessing the Places API.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.citation = self.valves.CITATION

    async def get_place_suggestions(
        self,
        query: str,
        location_bias: str = None,  # Example:  {"circle": {"center": {"latitude": 37.7937,"longitude": -122.3965 }, "radius": 500.0}}
        __event_emitter__: Callable[[dict], Any] = None,
        __user__: dict = {},
    ) -> str:
        """
        Provides place suggestions based on a text query and optional location bias using the Google Maps Text Search (New) API.
        :param query: The text query to search for (e.g., "restaurants in San Francisco").
        :param location_bias: (Optional) A location bias to prioritize results (e.g., circle around a lat/lng).
        :return: Details about the places found or an error message.
        """
        emitter = EventEmitter(__event_emitter__)

        try:
            await emitter.progress_update(f"Searching for places matching: {query}")

            # Determine which API key to use
            api_key = self.valves.GOOGLE_MAPS_API_KEY

            # Prepare the API request
            await emitter.progress_update(f"Fetching data for query: {query}")
            url = "https://places.googleapis.com/v1/places:searchText"  # Google Maps Text Search API endpoint

            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.primaryTypeDisplayName,places.formattedAddress,places.googleMapsLinks,places.reviews",  # Customize fields as needed
            }

            data = {
                "textQuery": query,
            }

            if location_bias:
                data["locationBias"] = location_bias

            # Make the API request
            response = requests.post(url, headers=headers, json=data)

            # Check if the request was successful
            if response.status_code != 200:
                raise Exception(
                    f"API request failed with status code: {response.status_code} - {response.text}"
                )

            # Parse and format the response
            place_data = response.text

            try:
                # Try to parse as JSON for better formatting
                place_json = json.loads(place_data)
                place_data = json.dumps(place_json, indent=2)
            except:
                # If not JSON, use the text as is
                pass

            formatted_output = f"Place suggestions for {query}:\n{place_data}"
            await emitter.success_update(f"Place suggestions for {query} retrieved!")
            return formatted_output

        except Exception as e:
            error_message = f"Error: {str(e)}"
            if "401" in str(e) or "403" in str(e):
                error_message += " (Potential Google Maps API Key issue. Please check your API key and ensure the Places API is enabled.)"
            await emitter.error_update(error_message)
            return error_message
