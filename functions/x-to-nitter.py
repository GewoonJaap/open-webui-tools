"""
title: X to Nitter Rewriter
author: GardenSnakes
author_url: https://github.com/GewoonJaap/open-webui-tools
version: 0.2.0
required_open_webui_version: 0.5.0
"""

from pydantic import BaseModel, Field
from typing import Callable, Awaitable, Any, Optional
import re
import asyncio


class Filter:
    class Valves(BaseModel):
        enabled: bool = Field(default=True, description="Enable X to Nitter rewriting.")
        status_updates: bool = Field(
            default=True, description="Show rewriting status updates."
        )
        pass

    def __init__(self):
        self.valves = self.Valves()
        # Matches both user and post URLs, with optional query parameters. Captures username AND status ID if present.
        self.x_to_nitter_pattern = re.compile(
            r"https?://(?:www\.)?x\.com/([a-zA-Z0-9_]+)(?:/status/(\d+))?(?:[?#].*)?"
        )

    async def inlet(
        self,
        body: dict,
        __event_emitter__: Callable[[Any], Awaitable[None]],
        __request__: Any,
        __user__: Optional[dict] = None,
        __model__: Optional[dict] = None,
    ) -> dict:
        messages = body["messages"]

        for message in messages:
            if message["role"] == "user" or message["role"] == "assistant":
                rewritten_content, urls_rewritten = await self.rewrite_x_to_nitter(
                    message["content"], __event_emitter__
                )
                message["content"] = rewritten_content

        # Also process tool outputs
        if "tool_calls" in body:
            for tool_call in body["tool_calls"]:
                if "content" in tool_call:
                    rewritten_content, urls_rewritten = await self.rewrite_x_to_nitter(
                        tool_call["content"], __event_emitter__
                    )
                    tool_call["content"] = rewritten_content

        return body

    async def rewrite_x_to_nitter(
        self, text: str, __event_emitter__: Callable[[Any], Awaitable[None]]
    ) -> tuple[str, int]:
        """Rewrites X.com links to Nitter.net and emits status updates."""
        urls_rewritten = 0
        rewritten_text_parts = []  # Accumulate text parts

        last_match_end = 0  # Track the end of the last match
        for match in self.x_to_nitter_pattern.finditer(text):
            original_url = match.group(0)
            username = match.group(1)
            status_id = match.group(2)  # Get the status ID

            # Add the text *before* the match
            rewritten_text_parts.append(text[last_match_end : match.start()])

            if self.valves.enabled:
                nitter_url = f"https://nitter.net/{username}"
                if status_id:
                    nitter_url += (
                        f"/status/{status_id}"  # Append the status ID if it exists
                    )

                if self.valves.status_updates:
                    await __event_emitter__(
                        {
                            "type": "status",
                            "data": {
                                "description": f"Rewriting X URL to Nitter: {original_url}",
                                "done": False,
                            },
                        }
                    )
                urls_rewritten += 1
                if self.valves.status_updates:
                    await __event_emitter__(
                        {
                            "type": "status",
                            "data": {
                                "description": f"Rewritten X URL to Nitter: {original_url} -> {nitter_url}",
                                "done": False,  # Not completely done, more might be coming
                            },
                        }
                    )

                rewritten_text_parts.append(nitter_url)  # add the nitter url
            else:
                rewritten_text_parts.append(original_url)

            last_match_end = match.end()  # update end position of match

        # Append any remaining text after the last match
        rewritten_text_parts.append(text[last_match_end:])

        rewritten_text = "".join(rewritten_text_parts)  # join the output to a string

        return rewritten_text, urls_rewritten
      
