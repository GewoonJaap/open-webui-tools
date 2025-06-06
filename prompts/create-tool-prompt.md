I want you to create a open web ui python tool. Here is an example of a tool: """
title: Flight Data Provider
author: GardenSnakes
author_url: https://github.com/GewoonJaap/open-webui-tools
description: A tool that returns flight data for a specified flight number using flight-status.com. Uses Jina to parse websites.
requirements: requests
version: 0.0.2
license: MIT
"""

import unittest
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
        GLOBAL_JINA_API_KEY: str = Field(
            default="",
            description="Global Jina API key for accessing the flight data API.",
        )

    class UserValves(BaseModel):
        JINA_API_KEY: str = Field(
            default="",
            description="(Optional) Jina API key. If provided, overrides the global API key.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.citation = self.valves.CITATION

    async def get_flight_data(
        self,
        flight_number: str,
        __event_emitter__: Callable[[dict], Any] = None,
        __user__: dict = {},
    ) -> str:
        """
        Provides detailed information about a specific flight using its flight number.
        Only use if the user has provided a valid flight number.
        Examples of valid flight numbers: UA123, DL456, AA789

        :param flight_number: The flight number to look up information for.
        :return: Details about the flight or an error message.
        """
        emitter = EventEmitter(__event_emitter__)

        # Initialize UserValves if not present
        if "valves" not in __user__:
            __user__["valves"] = self.UserValves()

        # Get user valves or create from dict if needed
        user_valves = __user__["valves"]
        if not isinstance(user_valves, self.UserValves) and isinstance(
            user_valves, dict
        ):
            try:
                user_valves = self.UserValves(**user_valves)
            except Exception as e:
                await emitter.progress_update(
                    f"Warning: Failed to parse user valves: {e}. Using defaults."
                )
                user_valves = self.UserValves()

        try:
            await emitter.progress_update(f"Validating flight number: {flight_number}")

            # Check if the flight number is valid
            if not flight_number or flight_number == "":
                raise Exception(f"Invalid flight number: {flight_number}")

            # Determine which API key to use
            api_key = user_valves.JINA_API_KEY or self.valves.GLOBAL_JINA_API_KEY

            # Prepare the API request
            await emitter.progress_update(f"Fetching data for flight {flight_number}")
            url = "https://r.jina.ai/"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            data = {"url": f"https://flight-status.com/{flight_number}"}

            # Make the API request
            response = requests.post(url, headers=headers, json=data)

            # Check if the request was successful
            if response.status_code != 200:
                raise Exception(
                    f"API request failed with status code: {response.status_code}"
                )

            # Parse and format the response
            flight_data = response.text

            try:
                # Try to parse as JSON for better formatting
                flight_json = json.loads(flight_data)
                flight_data = json.dumps(flight_json, indent=2)
            except:
                # If not JSON, use the text as is
                pass

            formatted_output = f"Flight data for {flight_number}:\n{flight_data}"
            await emitter.success_update(f"Flight data for {flight_number} retrieved!")
            return formatted_output

        except Exception as e:
            error_message = f"Error: {str(e)}"
            if "401" in str(e) or "403" in str(e):
                error_message += (
                    " (Potential Jina API Key issue. Please check your API key.)"
                )
            await emitter.error_update(error_message)
            return error_message


class FlightDataProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_get_flight_data_with_invalid_input(self):
        response = await Tools().get_flight_data("")
        self.assertTrue("Error" in response)

        response = await Tools().get_flight_data(None)
        self.assertTrue("Error" in response)


if __name__ == "__main__":
    print("Running tests...")
    unittest.main()




I want you to create: