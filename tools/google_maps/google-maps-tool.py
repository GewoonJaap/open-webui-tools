"""
title: Google Maps Text Search
author: GardenSnakes
author_url: https://github.com/GewoonJaap/open-webui-tools
description: A tool that returns place suggestions, including photos, full reviews, and emits citations (with specific source title), for a specified query using the Google Maps Text Search (New) API, formatted in Markdown.
requirements: requests
version: 0.0.9
license: MIT
"""

from typing import Any, Callable, List, Dict
import requests
import json
from pydantic import BaseModel, Field
from datetime import datetime # Added for citation
import asyncio # Added for citation

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
            if asyncio.iscoroutinefunction(self.event_emitter):
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
            else:
                self.event_emitter(
                    {
                        "type": "status",
                        "data": {
                            "status": status,
                            "description": description,
                            "done": done,
                        },
                    }
                )

    async def _emit_citation(self, url: str, title: str, content: str):
        """Emits a citation event if self.event_emitter is available."""
        if self.event_emitter:
            try:
                citation_data = {
                    "type": "citation",
                    "data": {
                        "document": [content], 
                        "metadata": [
                            {
                                "date_accessed": datetime.now().isoformat(),
                                "source": title, 
                            }
                        ],
                        "source": {"name": title, "url": url}, 
                    },
                }
                if asyncio.iscoroutinefunction(self.event_emitter):
                    await self.event_emitter(citation_data)
                else:
                    self.event_emitter(citation_data)
            except Exception as e:
                print(f"Error emitting citation event from EventEmitter for {url}: {e}")


class Tools:
    class Valves(BaseModel):
        CITATION: bool = Field(default="True", description="True or false for citation emission")
        GOOGLE_MAPS_API_KEY: str = Field(
            default="",
            description="Global Google Maps API key for accessing the Places API. This key will be used for all requests.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.citation_enabled = self.valves.CITATION

    async def get_place_suggestions(
        self,
        query: str,
        max_results: int = 3, 
        max_photo_width: int = 400,
        max_reviews_per_place: int = 5,
        __event_emitter__: Callable[[dict], Any] = None,
        __user__: dict = {}, 
    ) -> str:
        emitter = EventEmitter(__event_emitter__)

        try:
            await emitter.progress_update(f"Searching for places matching: {query}")

            api_key = self.valves.GOOGLE_MAPS_API_KEY
            if not api_key:
                 await emitter.error_update("Google Maps API Key is not configured.")
                 return "Error: Google Maps API Key is not configured. Please set it in the tool's valve settings."

            if not 1 <= max_results <= 20:
                await emitter.error_update(f"Invalid max_results value: {max_results}. Must be between 1 and 20.")
                return "Error: max_results must be between 1 and 20."
            
            if not 0 <= max_reviews_per_place <= 5:
                await emitter.error_update(f"Invalid max_reviews_per_place value: {max_reviews_per_place}. Must be between 0 and 5.")
                return "Error: max_reviews_per_place must be between 0 and 5."

            url = "https://places.googleapis.com/v1/places:searchText"
            field_mask = "places.displayName,places.formattedAddress,places.primaryTypeDisplayName,places.googleMapsUri,places.reviews,places.businessStatus,places.priceRange,places.rating,places.websiteUri,places.internationalPhoneNumber,places.photos"

            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": field_mask,
            }
            data = {"textQuery": query, "pageSize": max_results}

            await emitter.progress_update(f"Fetching data for query: {query} with {max_results} results.")
            response = requests.post(url, headers=headers, json=data)

            if response.status_code != 200:
                error_detail = response.text
                try:
                    error_json = response.json(); error_detail = error_json.get("error", {}).get("message", response.text)
                except json.JSONDecodeError: pass 
                raise Exception(f"API request failed with status code: {response.status_code} - {error_detail}")

            place_data_json = response.json()
            
            if not place_data_json.get("places"):
                await emitter.success_update(f"No places found for '{query}'.")
                return f"No places found matching your query: '{query}'."

            overall_markdown_output = f"# Place Suggestions for \"{query}\"\n\n"
            
            for i, place in enumerate(place_data_json.get("places", [])):
                place_markdown_content = "" 

                name = place.get("displayName", {}).get("text", "N/A")
                address = place.get("formattedAddress", "N/A")
                rating = place.get("rating", "N/A")
                website = place.get("websiteUri")
                maps_uri_from_api = place.get("googleMapsUri")
                maps_uri = maps_uri_from_api if maps_uri_from_api else f"https://www.google.com/maps/search/?api=1&query={name.replace(' ', '+').replace('&', '%26')}+{address.replace(' ', '+').replace('&', '%26')}"
                
                phone = place.get("internationalPhoneNumber", "N/A")
                status = place.get("businessStatus", "N/A")
                primary_type = place.get("primaryTypeDisplayName", {}).get("text", "N/A")

                place_markdown_content += f"## {i+1}. {name}\n"

                photos = place.get("photos", [])
                if photos:
                    photo_reference = photos[0].get("name") 
                    if photo_reference:
                        actual_photo_ref = photo_reference.split('/')[-1] if '/' in photo_reference else photo_reference
                        photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth={max_photo_width}&photoreference={actual_photo_ref}&key={api_key}"
                        place_markdown_content += f"![Photo of {name}]({photo_url})\n\n"

                place_markdown_content += f"- **Type**: {primary_type}\n"
                place_markdown_content += f"- **Address**: {address}\n"
                place_markdown_content += f"- **Rating**: {rating} ⭐\n"
                place_markdown_content += f"- **Status**: {status}\n"
                place_markdown_content += f"- **Phone**: {phone}\n"
                
                if website: place_markdown_content += f"- **Website**: [{website}]({website})\n"
                place_markdown_content += f"- **Google Maps**: [{maps_uri}]({maps_uri})\n"

                price_range_data = place.get("priceRange", {})
                if price_range_data:
                    start_price = price_range_data.get("startPrice", {}).get("units", ""); end_price = price_range_data.get("endPrice", {}).get("units", "")
                    currency = price_range_data.get("startPrice", {}).get("currencyCode", "")
                    if start_price and end_price and currency: place_markdown_content += f"- **Price Range**: {start_price} - {end_price} {currency}\n"
                    elif start_price and currency: place_markdown_content += f"- **Price Level**: {start_price} {currency}\n"

                reviews = place.get("reviews", [])
                if reviews and max_reviews_per_place > 0:
                    place_markdown_content += "- **Reviews**:\n"
                    for rev_idx, review in enumerate(reviews[:max_reviews_per_place]): 
                        rev_author = review.get("authorAttribution", {}).get("displayName", "Anonymous"); rev_rating = review.get("rating", "N/A")
                        original_text_info = review.get("originalText", {}); rev_text = original_text_info.get("text", review.get("text", {}).get("text", "No review text."))
                        place_markdown_content += f"  - **{rev_idx + 1}. {rev_author}** ({rev_rating} ⭐):\n"
                        for line in rev_text.split('\n'): place_markdown_content += f"    > {line}\n" 
                        place_markdown_content += "\n"
                place_markdown_content += "\n---\n\n"

                if self.citation_enabled and __event_emitter__:
                    # Format the citation title as requested
                    citation_title = f"Google Maps - {name}" 
                    await emitter._emit_citation( 
                        url=maps_uri, 
                        title=citation_title, # Use the newly formatted title 
                        content=place_markdown_content 
                    )
                
                overall_markdown_output += place_markdown_content

            await emitter.success_update(f"Place suggestions for {query} retrieved and formatted!")
            return overall_markdown_output

        except Exception as e:
            error_message = f"Error processing Google Maps request: {str(e)}"
            if "API key" in str(e) or "X-Goog-Api-Key" in str(e) or "403" in str(e) or "401" in str(e):
                error_message += " (Potential Google Maps API Key issue. Please check your API key and ensure the Places API is enabled in your Google Cloud Console.)"
            await emitter.error_update(error_message)
            return error_message
