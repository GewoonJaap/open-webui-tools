"""
title: X to Nitter Rewriter
author: GardenSnakes
author_url: https://github.com/GewoonJaap/open-webui-tools
funding_url: https://github.com/GewoonJaap/open-webui-tools  # Funding URL is same as author URL
version: 0.2.0
required_open_webui_version: 0.5.0
"""

from pydantic import BaseModel, Field
from typing import Callable, Awaitable, Any, Optional
import re
import asyncio
import json


class EventEmitter:
    def __init__(self, event_emitter: Callable[[dict], Any] = None):
        self.event_emitter = event_emitter

    async def progress_update(self, description):
        await self.emit(description)

    async def complete_update(self, description):
        await self.emit(description, "success", True)  # use to mark complete.

    async def error_update(self, description):
        await self.emit(description, "error", True)

    async def success_update(self, description):
        await self.emit(description, "success", False)

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


class Filter:
    class Valves(BaseModel):
        enabled: bool = Field(default=True, description="Enable X to Nitter rewriting.")
        status_updates: bool = Field(default=True, description="Show rewriting status updates.")
        with_replies: bool = Field(default=False, description="Append /with_replies to user profile URLs.")
        process_tool_args: bool = Field(default=True, description="Process JSON Args in Tool Functions (If Valid JSON)") # Added option so that it can be turned off.
        pass

    def __init__(self):
        self.valves = self.Valves()
        # Matches both user and post URLs, with optional query parameters. Captures username AND status ID if present.
        self.x_to_nitter_pattern = re.compile(
            r"https?://(?:www\.)?x\.com/([a-zA-Z0-9_]+)(?:/status/(\d+))?(?:[?#].*)?")

    async def inlet(
            self,
            body: dict,
            __event_emitter__: Callable[[Any], Awaitable[None]],
            __request__: Any,
            __user__: Optional[dict] = None,
            __model__: Optional[dict] = None,
    ) -> dict:
        emitter = EventEmitter(__event_emitter__)

        messages = body["messages"]

        for message in messages:
            if message["role"] == "user" or message["role"] == "assistant":
                rewritten_content, urls_rewritten = await self.rewrite_x_to_nitter(message["content"], __event_emitter__)
                message["content"] = rewritten_content

        # Also process tool outputs
        if "tool_calls" in body:
            for tool_call in body["tool_calls"]:
                if "content" in tool_call:
                    rewritten_content, urls_rewritten = await self.rewrite_x_to_nitter(tool_call["content"], __event_emitter__)
                    tool_call["content"] = rewritten_content

        # Process tool outputs for the 'new' format
        if "response" in body and body["response"] and "tool_calls" in body["response"]:
            for tool_call in body["response"]["tool_calls"]:
                if "function" in tool_call and "arguments" in tool_call["function"] and self.valves.process_tool_args:
                    arguments = tool_call["function"]["arguments"]
                    if isinstance(arguments, str):
                        try:
                            arguments_json = json.loads(arguments)
                            for key, value in arguments_json.items():
                                if isinstance(value, str):
                                    rewritten_value, _ = await self.rewrite_x_to_nitter(value, __event_emitter__)
                                    arguments_json[key] = rewritten_value
                            tool_call["function"]["arguments"] = json.dumps(arguments_json)  # puts the changes back in
                        except json.JSONDecodeError:
                            print("Error decoding tool call arguments JSON.")
                if "content" in tool_call:  # Added to account for tool calls that return string content directly
                    rewritten_content, urls_rewritten = await self.rewrite_x_to_nitter(tool_call["content"], __event_emitter__)
                    tool_call["content"] = rewritten_content
        await emitter.complete_update("All X URLs rewritten to Nitter (if enabled).")  # Completion status after all is done

        return body

    async def rewrite_x_to_nitter(self, text: str, __event_emitter__: Callable[[Any], Awaitable[None]]) -> tuple[str, int]:
        """Rewrites X.com links to Nitter.net and emits status updates."""
        emitter = EventEmitter(__event_emitter__)  # Create emitter local to the function.
        urls_rewritten = 0
        rewritten_text_parts = []  # Accumulate text parts

        last_match_end = 0  # Track the end of the last match
        for match in self.x_to_nitter_pattern.finditer(text):
            original_url = match.group(0)
            username = match.group(1)
            status_id = match.group(2)  # Get the status ID

            # Add the text *before* the match
            rewritten_text_parts.append(text[last_match_end:match.start()])

            if self.valves.enabled:
                nitter_url = f"https://nitter.net/{username}"
                if status_id:
                    nitter_url += f"/status/{status_id}"  # Append the status ID if it exists
                elif self.valves.with_replies:
                    nitter_url += "/with_replies"  # Append the with_replies if it exists.

                if self.valves.status_updates:
                    await emitter.progress_update(f"Rewriting X URL to Nitter: {original_url}")
                urls_rewritten += 1
                if self.valves.status_updates:
                    await emitter.success_update(f"Rewritten X URL to Nitter: {original_url} -> {nitter_url}")

                rewritten_text_parts.append(nitter_url)  # add the nitter url
            else:
                rewritten_text_parts.append(original_url)

            last_match_end = match.end()  # update end position of match

        # Append any remaining text after the last match
        rewritten_text_parts.append(text[last_match_end:])

        rewritten_text = "".join(rewritten_text_parts)  # join the output to a string

        return rewritten_text, urls_rewritten
