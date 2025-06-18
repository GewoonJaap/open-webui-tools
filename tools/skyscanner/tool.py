"""
title: Skyscanner Flight Search and Price Calendar
author: AI Assistant
author_url: https://github.com/openai
description: A tool to search for flights, get a price calendar, or find the cheapest round-trip window. Uses Requests.
requirements: requests, pydantic
version: 0.1.3
license: MIT
"""

from typing import Any, Callable, Dict, List
import json
import requests
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import uuid
import time
import asyncio


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
            event_data = {
                "type": "status",
                "data": {
                    "status": status,
                    "description": description,
                    "done": done,
                },
            }
            if asyncio.iscoroutinefunction(self.event_emitter):
                await self.event_emitter(event_data)
            else:
                self.event_emitter(event_data)

    async def _emit_citation(self, url: str, title: str, content: str):
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
        CITATION: bool = Field(default=True, description="True or false for citation")
        MAX_POLL_ATTEMPTS: int = Field(
            default=15, description="Maximum attempts to poll for flight results."
        )
        POLL_DELAY_SECONDS: float = Field(
            default=3.0, description="Delay in seconds between polling attempts."
        )

    def __init__(self):
        self.valves = self.Valves()
        self.skyscanner_base_url = "https://www.skyscanner.nl"

    async def _get_place_details(
        self,
        place_name: str,
        emitter: Any,
        is_destination: bool = False,
    ) -> Dict[str, str]:
        await emitter.progress_update(f"Fetching details for '{place_name}'...")
        encoded_place_name = place_name.replace(" ", "%20")
        url = f"{self.skyscanner_base_url}/g/autosuggest-search/api/v1/search-flight/NL/nl-NL/{encoded_place_name}?isDestination={str(is_destination).lower()}&enable_general_search_v2=true&autosuggestExp="

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) Gecko/20100101 Firefox/139.0",
            "Accept": "application/json",
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            results = response.json()
            if not results:
                raise ValueError(f"No place details found for '{place_name}'.")

            place_data = results[0]

            details = {
                "geo_id": place_data.get("GeoId"),
                "place_id_iata": place_data.get("IataCode")
                or place_data.get("PlaceId"),
                "name": place_data.get("PlaceName"),
                "city_geo_id": (
                    place_data.get("GeoContainerId")
                    if place_data.get("GeoContainerId")
                    else place_data.get("GeoId")
                ),
                "display_code": place_data.get("IataCode") or place_data.get("PlaceId"),
            }
            if not details["geo_id"] or not details["place_id_iata"]:
                raise ValueError(
                    f"Could not extract GeoId or IATA-equivalent ID for '{place_name}'. Data: {place_data}"
                )
            await emitter.progress_update(
                f"Details found for {place_name}: {details['name']} ({details['display_code']})"
            )
            return details
        except requests.exceptions.RequestException as e:
            await emitter.error_update(
                f"Network error fetching details for {place_name}: {e}"
            )
            raise ValueError(f"Network error fetching details for {place_name}: {e}")
        except (json.JSONDecodeError, IndexError, KeyError, ValueError) as e:
            await emitter.error_update(
                f"Error processing details for {place_name}: {e}"
            )
            raise ValueError(f"Error processing details for {place_name}: {e}")

    def _format_date_for_api(self, date_str: str) -> Dict[str, str]:
        try:
            dt_obj = datetime.strptime(date_str, "%Y-%m-%d")
            return {
                "@type": "date",
                "year": dt_obj.strftime("%Y"),
                "month": dt_obj.strftime("%m"),
                "day": dt_obj.strftime("%d"),
            }
        except ValueError:
            raise ValueError(
                f"Invalid date format: '{date_str}'. Please use YYYY-MM-DD."
            )

    def _get_total_duration(self, itinerary: Dict) -> float:
        total_duration = 0
        legs = itinerary.get("legs", [])
        if len(legs) == 2:
            for leg in legs:
                total_duration += leg.get("durationInMinutes", 0)
            return total_duration
        return float("inf")

    def _minutes_to_hm_str(self, minutes: Any) -> str:
        if (
            not isinstance(minutes, (int, float))
            or minutes == float("inf")
            or minutes < 0
        ):
            return "N/A"
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hours}h {mins:02d}m"

    def _format_itinerary_details(self, itinerary: Dict, rank: int) -> List[str]:
        lines = []
        price = itinerary.get("price", {}).get("formatted", "N/A")
        score = itinerary.get("score", "N/A")
        total_duration_minutes = self._get_total_duration(itinerary)
        total_duration_str = self._minutes_to_hm_str(total_duration_minutes)

        lines.append(f"  Option {rank}:")
        lines.append(f"    Price: {price}")
        lines.append(f"    Total Duration: {total_duration_str}")
        lines.append(
            f"    Skyscanner Score: {score:.3f}"
            if isinstance(score, float)
            else f"    Skyscanner Score: {score}"
        )

        deeplink_url = "N/A"
        pricing_options = itinerary.get("pricingOptions", [])
        if pricing_options:
            first_pricing_option_items = pricing_options[0].get("items", [])
            if first_pricing_option_items:
                relative_url = first_pricing_option_items[0].get("url")
                if relative_url:
                    deeplink_url = f"{self.skyscanner_base_url}{relative_url}"
        lines.append(f"    Deeplink: {deeplink_url}")

        legs_data = itinerary.get("legs", [])
        if len(legs_data) == 2:
            for leg_idx, leg in enumerate(legs_data):
                leg_type = "Outbound" if leg_idx == 0 else "Return"
                leg_duration_str = self._minutes_to_hm_str(
                    leg.get("durationInMinutes", "N/A")
                )
                lines.append(
                    f"    {leg_type} Leg: Duration: {leg_duration_str}, Stops: {leg.get('stopCount', 'N/A')}"
                )
        lines.append("")
        return lines

    async def search_flights(
        self,
        origin_airport_name: str,
        destination_airport_name: str,
        departure_date: str,
        return_date: str,
        passengers: int = 1,
        __event_emitter__: Callable[[dict], Any] = None,
        __user__: dict = {},
    ) -> str:
        """
        Searches for bookable round-trip flights for specific dates.

        This function finds actual, bookable flights and returns the top 3 options categorized by price, speed, and Skyscanner's recommendation.
        Use this when the user has provided exact dates for their travel.

        :param origin_airport_name: The starting airport or city. Can be an IATA code or a name. Examples: "AMS", "Amsterdam", "New York JFK".
        :param destination_airport_name: The destination airport or city. Can be an IATA code or a name. Examples: "LHR", "London Heathrow".
        :param departure_date: The outbound flight date. Must be in YYYY-MM-DD format. Example: "2024-12-25".
        :param return_date: The return flight date. Must be in YYYY-MM-DD format. Example: "2025-01-05".
        :param passengers: The number of adult passengers traveling. Default is 1.
        :return: A formatted string containing the top flight options, each with a deeplink for booking.
        """
        emitter = EventEmitter(__event_emitter__)

        try:
            await emitter.progress_update("Validating inputs for flight search...")
            if not all(
                [
                    origin_airport_name,
                    destination_airport_name,
                    departure_date,
                    return_date,
                ]
            ):
                raise ValueError(
                    "Origin, destination, departure date, and return date must be provided."
                )
            if not isinstance(passengers, int) or passengers <= 0:
                raise ValueError("Number of passengers must be a positive integer.")

            formatted_departure_date_api = self._format_date_for_api(departure_date)
            formatted_return_date_api = self._format_date_for_api(return_date)

            dep_dt_obj = datetime.strptime(departure_date, "%Y-%m-%d")
            ret_dt_obj = datetime.strptime(return_date, "%Y-%m-%d")
            dep_yymmdd = dep_dt_obj.strftime("%y%m%d")
            ret_yymmdd = ret_dt_obj.strftime("%y%m%d")

            origin_details = await self._get_place_details(
                origin_airport_name, emitter, is_destination=False
            )
            destination_details = await self._get_place_details(
                destination_airport_name, emitter, is_destination=True
            )

            traveller_context_id = str(uuid.uuid4())
            view_id = str(uuid.uuid4())

            referer_url = f"{self.skyscanner_base_url}/transport/vluchten/{origin_details['place_id_iata'].lower()}/{destination_details['place_id_iata'].lower()}/{dep_yymmdd}/{ret_yymmdd}/?adultsv2={passengers}&cabinclass=economy&childrenv2=&ref=home&rtn=1&preferdirects=false&outboundaltsenabled=false&inboundaltsenabled=false"

            search_payload = {
                "cabinClass": "ECONOMY",
                "childAges": [],
                "adults": passengers,
                "legs": [
                    {
                        "legOrigin": {
                            "@type": "entity",
                            "entityId": origin_details["geo_id"],
                        },
                        "legDestination": {
                            "@type": "entity",
                            "entityId": destination_details["geo_id"],
                        },
                        "dates": formatted_departure_date_api,
                        "placeOfStay": destination_details["city_geo_id"],
                    },
                    {
                        "legOrigin": {
                            "@type": "entity",
                            "entityId": destination_details["geo_id"],
                        },
                        "legDestination": {
                            "@type": "entity",
                            "entityId": origin_details["geo_id"],
                        },
                        "dates": formatted_return_date_api,
                    },
                ],
            }

            base_search_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) Gecko/20100101 Firefox/139.0",
                "Accept": "application/json",
                "Accept-Language": "nl,en-US;q=0.7,en;q=0.3",
                "X-Skyscanner-ChannelId": "website",
                "X-Skyscanner-Consent-Adverts": "true",
                "X-Skyscanner-Traveller-Context": traveller_context_id,
                "X-Skyscanner-ViewId": view_id,
                "X-Skyscanner-Ads-Sponsored-View-Type": "ADS_SPONSORED_VIEW_DAY_VIEW",
                "X-Skyscanner-Combined-Results-Rail": "true",
                "X-Skyscanner-Market": "NL",
                "X-Skyscanner-Locale": "nl-NL",
                "X-Skyscanner-Currency": "EUR",
                "X-Skyscanner-TrustedFunnelId": view_id,
                "Alt-Used": "www.skyscanner.nl",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Referer": referer_url,
            }
            post_headers = {**base_search_headers, "Content-Type": "application/json"}

            await emitter.progress_update(
                f"Initiating flight search from {origin_details['name']} to {destination_details['name']}..."
            )
            search_url_base = (
                f"{self.skyscanner_base_url}/g/radar/api/v2/web-unified-search/"
            )

            flight_data = None
            session_id_from_post = None

            try:
                response = requests.post(
                    search_url_base,
                    json=search_payload,
                    headers=post_headers,
                    timeout=15,
                )
                response_text = response.text
                response.raise_for_status()
                flight_data = response.json()
                session_id_from_post = flight_data.get("context", {}).get("sessionId")
                if not session_id_from_post:
                    raise ValueError("Missing sessionId in initial search response.")
                await emitter.progress_update(
                    "Initial search request successful. Session ID obtained."
                )
            except requests.exceptions.HTTPError as e:
                await emitter.error_update(
                    f"Skyscanner API error (POST): {e}. Response: {response_text[:500]}"
                )
                return f"Error: Skyscanner API request failed (POST) ({e.response.status_code}). Response: {response_text[:500]}"
            except (
                requests.exceptions.RequestException,
                json.JSONDecodeError,
                ValueError,
            ) as e:
                await emitter.error_update(
                    f"An error occurred during initial search: {type(e).__name__} - {e}"
                )
                return f"An error occurred during initial search: {e}"

            for attempt in range(self.valves.MAX_POLL_ATTEMPTS):
                status = flight_data.get("context", {}).get("status", "unknown")
                total_results_count = (
                    flight_data.get("itineraries", {})
                    .get("context", {})
                    .get("totalResults", 0)
                )
                await emitter.progress_update(
                    f"Polling for results... Attempt {attempt + 1}/{self.valves.MAX_POLL_ATTEMPTS}. Status: {status}, Results so far: {total_results_count}"
                )

                if status == "complete":
                    await emitter.progress_update(
                        "Search complete. All results received."
                    )
                    break
                if status != "incomplete":
                    await emitter.error_update(
                        f"Search ended with unexpected status: {status}."
                    )
                    break
                if attempt == self.valves.MAX_POLL_ATTEMPTS - 1:
                    await emitter.error_update(
                        f"Max polling attempts reached. Search may be incomplete."
                    )
                    break

                time.sleep(self.valves.POLL_DELAY_SECONDS)
                polling_url = f"{search_url_base}{session_id_from_post}"
                try:
                    poll_response = requests.get(
                        polling_url, headers=base_search_headers, timeout=15
                    )
                    poll_response_text = poll_response.text
                    poll_response.raise_for_status()
                    flight_data = poll_response.json()
                    new_session_id = flight_data.get("context", {}).get("sessionId")
                    if new_session_id:
                        session_id_from_post = new_session_id
                    else:
                        await emitter.error_update(
                            "Session ID missing in polling response."
                        )
                        break
                except (
                    requests.exceptions.RequestException,
                    json.JSONDecodeError,
                ) as e:
                    await emitter.error_update(
                        f"An error occurred during polling: {type(e).__name__} - {e}"
                    )
                    break

            itineraries_data = flight_data.get("itineraries", {})
            all_results = itineraries_data.get("results", [])
            final_status = flight_data.get("context", {}).get("status", "unknown")

            if not all_results:
                msg = f"No flight results found after polling. Final status: {final_status}."
                await emitter.success_update(msg)
                return msg

            output_lines = [
                f"Flight Search Summary (Total found: {itineraries_data.get('context', {}).get('totalResults', len(all_results))}, API Status: {final_status}):\n"
            ]

            cheapest_flights = sorted(
                all_results, key=lambda x: x.get("price", {}).get("raw", float("inf"))
            )
            output_lines.append("--- Top 3 Cheapest Flights ---")
            if not cheapest_flights:
                output_lines.append("  No flights found for this category.")
            else:
                [
                    output_lines.extend(
                        self._format_itinerary_details(itinerary, i + 1)
                    )
                    for i, itinerary in enumerate(cheapest_flights[:3])
                ]
            output_lines.append("")

            fastest_flights = sorted(all_results, key=self._get_total_duration)
            output_lines.append("--- Top 3 Fastest Flights ---")
            if not fastest_flights:
                output_lines.append("  No flights found for this category.")
            else:
                [
                    output_lines.extend(
                        self._format_itinerary_details(itinerary, i + 1)
                    )
                    for i, itinerary in enumerate(fastest_flights[:3])
                ]
            output_lines.append("")

            recommended_flights = sorted(
                all_results, key=lambda x: x.get("score", 0.0), reverse=True
            )
            output_lines.append(
                "--- Top 3 Recommended Flights (by Skyscanner score) ---"
            )
            if not recommended_flights:
                output_lines.append("  No flights found for this category.")
            else:
                [
                    output_lines.extend(
                        self._format_itinerary_details(itinerary, i + 1)
                    )
                    for i, itinerary in enumerate(recommended_flights[:3])
                ]

            final_output = "\n".join(output_lines)

            if self.valves.CITATION:
                citation_title = f"Skyscanner Flight Search: {origin_airport_name} to {destination_airport_name}"
                await emitter._emit_citation(
                    url=referer_url, title=citation_title, content=final_output
                )
                final_output += (
                    f"\n\nData provided by Skyscanner ({self.skyscanner_base_url})"
                )

            llm_instruction = "\n\n[LLM Guide: When presenting these flight options to the user, highlight the price and total duration. For each flight option, you **must** include its full 'Deeplink' URL to allow the user to proceed with booking. Emphasize that these are the best options found for the cheapest, fastest, and recommended categories.]"
            final_output += llm_instruction

            await emitter.success_update(
                "Flight search processing complete. Results formatted."
            )
            return final_output

        except (ValueError, Exception) as e:
            error_message = f"An error occurred: {type(e).__name__} - {str(e)}"
            await emitter.error_update(error_message)
            return error_message

    async def _fetch_calendar_data(
        self, origin_sky_id: str, destination_sky_id: str, emitter: Any
    ) -> List[Dict]:
        """Internal helper to fetch and return raw calendar day data."""
        await emitter.progress_update(
            f"Fetching price calendar for {origin_sky_id} to {destination_sky_id}..."
        )
        payload = {
            "headers": {
                "xSkyscannerClient": "banana",
                "xSkyscannerCurrency": "EUR",
                "xSkyscannerLocale": "nl-NL",
                "xSkyscannerMarket": "NL",
            },
            "originRelevantFlightSkyId": origin_sky_id,
            "destinationRelevantFlightSkyId": destination_sky_id,
        }
        request_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) Gecko/20100101 Firefox/139.0",
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Referer": self.skyscanner_base_url,
        }
        calendar_url = f"{self.skyscanner_base_url}/g/search-intent/v1/pricecalendar"
        try:
            response = requests.post(
                calendar_url, json=payload, headers=request_headers, timeout=15
            )
            response.raise_for_status()
            return response.json().get("flights", {}).get("days", [])
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            await emitter.error_update(
                f"Failed to fetch calendar data for {origin_sky_id} -> {destination_sky_id}: {e}"
            )
            return None

    async def find_cheapest_round_trip_by_calendar(
        self,
        origin_airport_name: str,
        destination_airport_name: str,
        trip_duration_days: int = 7,
        __event_emitter__: Callable[[dict], Any] = None,
        __user__: dict = {},
    ) -> str:
        """
        Finds the cheapest travel dates for a round trip of a given duration using the price calendar.

        Use this function when the user is flexible with their travel dates and wants to find the most affordable period to travel.
        This provides an *indicative* price, not a final bookable fare.

        :param origin_airport_name: The starting airport or city. Examples: "AMS", "Amsterdam".
        :param destination_airport_name: The destination airport or city. Examples: "BCN", "Barcelona".
        :param trip_duration_days: The desired length of the trip in days. For example, 7 for a week-long trip. Default is 7.
        :return: A string with the best found dates and the total indicative price for the round trip.
        """
        emitter = EventEmitter(__event_emitter__)

        try:
            await emitter.progress_update(
                "Validating inputs for cheapest trip search..."
            )
            if not origin_airport_name or not destination_airport_name:
                raise ValueError("Origin and destination must be provided.")
            if not isinstance(trip_duration_days, int) or trip_duration_days <= 0:
                raise ValueError("Trip duration must be a positive number of days.")

            origin_details = await self._get_place_details(
                origin_airport_name, emitter, is_destination=False
            )
            destination_details = await self._get_place_details(
                destination_airport_name, emitter, is_destination=True
            )

            origin_sky_id = origin_details["place_id_iata"]
            destination_sky_id = destination_details["place_id_iata"]

            outbound_days_raw = await self._fetch_calendar_data(
                origin_sky_id, destination_sky_id, emitter
            )
            return_days_raw = await self._fetch_calendar_data(
                destination_sky_id, origin_sky_id, emitter
            )

            if outbound_days_raw is None or return_days_raw is None:
                return "Could not retrieve price calendar data for one or both directions. Please try again."

            outbound_prices = {
                day["day"]: day["price"]
                for day in outbound_days_raw
                if day.get("price") is not None
            }
            return_prices = {
                day["day"]: day["price"]
                for day in return_days_raw
                if day.get("price") is not None
            }

            if not outbound_prices or not return_prices:
                return "No pricing information available in the calendar to find a cheap trip."

            best_price = float("inf")
            best_outbound_date = None
            best_return_date = None
            currency = "EUR"

            await emitter.progress_update(
                f"Calculating cheapest {trip_duration_days}-day trip..."
            )
            for out_date_str, out_price in outbound_prices.items():
                try:
                    out_date = datetime.strptime(out_date_str, "%Y-%m-%d")
                    return_date_str = (
                        out_date + timedelta(days=trip_duration_days)
                    ).strftime("%Y-%m-%d")
                    if return_date_str in return_prices:
                        total_price = out_price + return_prices[return_date_str]
                        if total_price < best_price:
                            best_price = total_price
                            best_outbound_date = out_date_str
                            best_return_date = return_date_str
                except (ValueError, TypeError):
                    continue

            if best_outbound_date is None:
                return f"Could not find any available round-trip options for a {trip_duration_days}-day trip within the calendar's date range."

            final_output = "\n".join(
                [
                    f"Cheapest Indicative Price for a {trip_duration_days}-day Round Trip:",
                    f"  - Outbound Date: {best_outbound_date}",
                    f"  - Return Date:   {best_return_date}",
                    f"  - Total Indicative Price: {best_price:.2f} {currency}",
                ]
            )

            if self.valves.CITATION:
                citation_url = f"{self.skyscanner_base_url}/transport/vluchten/{origin_sky_id.lower()}/{destination_sky_id.lower()}/"
                await emitter._emit_citation(
                    url=citation_url,
                    title=f"Skyscanner Price Calendar: {origin_airport_name} to {destination_airport_name}",
                    content=final_output,
                )
                final_output += (
                    f"\n\nData provided by Skyscanner ({self.skyscanner_base_url})"
                )

            llm_instruction = "\n\n[LLM Guide: Present the found dates and the total indicative price clearly to the user. Crucially, explain that this price is based on the flight calendar and is not a final, bookable fare. Advise the user to use the `search_flights` tool with these exact dates to find specific flights and get booking links.]"
            final_output += llm_instruction

            await emitter.success_update("Cheapest round trip window found.")
            return final_output

        except (ValueError, Exception) as e:
            error_message = f"An error occurred: {type(e).__name__} - {str(e)}"
            await emitter.error_update(error_message)
            return error_message

    async def get_flight_price_calendar(
        self,
        origin_airport_name: str,
        destination_airport_name: str,
        __event_emitter__: Callable[[dict], Any] = None,
        __user__: dict = {},
    ) -> str:
        """
        Retrieves a one-way flight price calendar for a given route.

        This function is useful for getting a general overview of price fluctuations for one-way travel over the next few months.
        The prices shown are indicative and not final bookable fares.

        :param origin_airport_name: The starting airport or city. Examples: "AMS", "Amsterdam".
        :param destination_airport_name: The destination airport or city. Examples: "LHR", "London".
        :return: A formatted string listing dates and their indicative one-way prices.
        """
        emitter = EventEmitter(__event_emitter__)
        try:
            await emitter.progress_update("Validating inputs for price calendar...")
            if not origin_airport_name or not destination_airport_name:
                raise ValueError("Origin and destination must be provided.")

            origin_details = await self._get_place_details(
                origin_airport_name, emitter, is_destination=False
            )
            destination_details = await self._get_place_details(
                destination_airport_name, emitter, is_destination=True
            )

            days = await self._fetch_calendar_data(
                origin_details["place_id_iata"],
                destination_details["place_id_iata"],
                emitter,
            )

            if days is None:
                return "Could not retrieve price calendar data. Please try again."
            if not days:
                return "No price calendar data available for this route."

            currency = "EUR"
            output_lines = [
                f"Flight Price Calendar for {origin_details['name']} to {destination_details['name']} (Prices in {currency}):\n"
            ]
            for day_info in days:
                date_str = day_info.get("day")
                price = day_info.get("price")
                group = day_info.get("group", "")
                if price is not None:
                    output_lines.append(
                        f"  - {date_str}: {price:.2f} {currency} (Group: {group if group else 'N/A'})"
                    )
                else:
                    output_lines.append(
                        f"  - {date_str}: No price information (Group: {group if group else 'N/A'})"
                    )

            final_output = "\n".join(output_lines)
            if self.valves.CITATION:
                citation_url = f"{self.skyscanner_base_url}/transport/vluchten/{origin_details['place_id_iata'].lower()}/{destination_details['place_id_iata'].lower()}/"
                await emitter._emit_citation(
                    url=citation_url,
                    title=f"Skyscanner Price Calendar: {origin_airport_name} to {destination_airport_name}",
                    content=final_output,
                )
                final_output += (
                    f"\n\nData provided by Skyscanner ({self.skyscanner_base_url})"
                )

            await emitter.success_update(
                "Flight price calendar successfully retrieved."
            )
            return final_output

        except (ValueError, Exception) as e:
            error_message = f"An error occurred: {type(e).__name__} - {str(e)}"
            await emitter.error_update(error_message)
            return error_message
