"""
title: Antigravity Proxy Connector for OpenWebUI
version: 1.0.0
description: Access Gemini and Claude models via Antigravity Proxy directly within OpenWebUI.
author: Logappradeep
author_url: https://github.com/logappradeep-m/antigravity-proxy-openwebui
license: MIT
"""

import json
import requests
import traceback
from typing import Optional, List, Union, Generator, Iterator
from pydantic import BaseModel, Field


class Pipe:
    """
    OpenWebUI Pipe that connects to the Antigravity Proxy.

    The proxy exposes an Anthropic-compatible Messages API backed by
    Antigravity's Cloud Code, providing access to and Gemini models.
    """

    class Valves(BaseModel):
        PROXY_BASE_URL: str = Field(
            default="http://localhost:8080",
            description="Base URL of the Antigravity Proxy server.",
        )
        API_KEY: str = Field(
            default="test",
            description="API key for the proxy (default 'test' if no API key is configured on the proxy).",
        )
        INCLUDE_THINKING: bool = Field(
            default=True,
            description="Include reasoning/thinking tokens in the response for models that support it (e.g., claude-*-thinking, gemini-3+).",
        )
        MODEL_PREFIX: Optional[str] = Field(
            default="AG-Proxy: ",
            description="Optional prefix for model names displayed in OpenWebUI (e.g., 'AG-Proxy: ').",
        )
        REQUEST_TIMEOUT: int = Field(
            default=300,
            description="Timeout for API requests in seconds.",
            gt=0,
        )
        STREAM_TIMEOUT: int = Field(
            default=600,
            description="Timeout for streaming API requests in seconds.",
            gt=0,
        )

    def __init__(self):
        self.type = "manifold"
        self.valves = self.Valves()

    def pipes(self) -> List[dict]:
        """
        Fetch available models from the Antigravity Proxy.
        Called by OpenWebUI to discover models this pipe provides.
        """
        try:
            headers = self._get_headers()
            response = requests.get(
                f"{self.valves.PROXY_BASE_URL}/v1/models",
                headers=headers,
                timeout=self.valves.REQUEST_TIMEOUT,
            )
            response.raise_for_status()

            models_data = response.json()
            raw_models = models_data.get("data", [])
            models: List[dict] = []

            for model in raw_models:
                model_id = model.get("id")
                if not model_id:
                    continue

                model_name = model.get("description") or model.get("name") or model_id
                prefix = self.valves.MODEL_PREFIX or ""
                models.append({"id": model_id, "name": f"{prefix}{model_name}"})

            if not models:
                return [
                    {
                        "id": "error",
                        "name": "Pipe Error: No models found on Antigravity Proxy",
                    }
                ]

            return models

        except requests.exceptions.ConnectionError:
            return [
                {
                    "id": "error",
                    "name": "Pipe Error: Cannot connect to Antigravity Proxy. Is it running?",
                }
            ]
        except requests.exceptions.Timeout:
            return [
                {"id": "error", "name": "Pipe Error: Timeout connecting to proxy"}
            ]
        except requests.exceptions.HTTPError as e:
            error_msg = f"Pipe Error: HTTP {e.response.status_code} fetching models"
            try:
                error_detail = (
                    e.response.json().get("error", {}).get("message", "")
                )
                if error_detail:
                    error_msg += f": {error_detail}"
            except (json.JSONDecodeError, AttributeError):
                pass
            return [{"id": "error", "name": error_msg}]
        except Exception as e:
            traceback.print_exc()
            return [{"id": "error", "name": f"Pipe Error: {e}"}]

    def pipe(self, body: dict) -> Union[str, Generator, Iterator]:
        """
        Process chat requests by forwarding them to the Antigravity Proxy.

        The proxy accepts Anthropic Messages API format, so we convert from
        OpenAI-style messages to Anthropic format and back.
        """
        try:
            # Extract model ID - OpenWebUI prepends the pipe name with a dot separator
            model_id = body.get("model", "")
            if "." in model_id:
                model_id = model_id.split(".", 1)[1]

            # Convert OpenAI-style messages to Anthropic format
            messages = body.get("messages", [])
            anthropic_messages, system_prompt = self._convert_messages(messages)

            # Build Anthropic API request
            payload = {
                "model": model_id,
                "messages": anthropic_messages,
                "max_tokens": body.get("max_tokens", 8192),
                "stream": body.get("stream", False),
            }

            # Add system prompt if present
            if system_prompt:
                payload["system"] = system_prompt

            # Add thinking support for thinking-capable models
            if self.valves.INCLUDE_THINKING and self._is_thinking_model(model_id):
                payload["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": min(
                        body.get("max_tokens", 8192) * 2, 32768
                    ),
                }

            # Forward optional parameters
            if body.get("temperature") is not None:
                payload["temperature"] = body["temperature"]
            if body.get("top_p") is not None:
                payload["top_p"] = body["top_p"]
            if body.get("top_k") is not None:
                payload["top_k"] = body["top_k"]

            # Forward tools if present
            if body.get("tools"):
                payload["tools"] = self._convert_tools(body["tools"])

            headers = self._get_headers()
            headers["Content-Type"] = "application/json"
            url = f"{self.valves.PROXY_BASE_URL}/v1/messages"
            is_streaming = body.get("stream", False)

            if is_streaming:
                return self._stream_response(url, headers, payload)
            else:
                return self._non_stream_response(url, headers, payload)

        except Exception as e:
            traceback.print_exc()
            return f"Pipe Error: {e}"

    def _get_headers(self) -> dict:
        """Build request headers with authentication."""
        return {
            "x-api-key": self.valves.API_KEY,
            "Authorization": f"Bearer {self.valves.API_KEY}",
        }

    def _is_thinking_model(self, model_id: str) -> bool:
        """Check if a model supports thinking/reasoning output."""
        lower = model_id.lower()
        if "thinking" in lower:
            return True
        # Gemini 3+ models support thinking natively
        if "gemini" in lower:
            import re

            match = re.search(r"gemini-(\d+)", lower)
            if match and int(match.group(1)) >= 3:
                return True
        return False

    def _convert_messages(self, messages: list) -> tuple:
        """
        Convert OpenAI-style messages to Anthropic Messages API format.

        Returns:
            tuple: (anthropic_messages, system_prompt)
        """
        system_prompt = None
        anthropic_messages = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # Extract system messages
            if role == "system":
                if isinstance(content, str):
                    system_prompt = (
                        f"{system_prompt}\n{content}" if system_prompt else content
                    )
                elif isinstance(content, list):
                    text_parts = [
                        p.get("text", "") for p in content if p.get("type") == "text"
                    ]
                    sys_text = "\n".join(text_parts)
                    system_prompt = (
                        f"{system_prompt}\n{sys_text}" if system_prompt else sys_text
                    )
                continue

            # Convert content to Anthropic format
            if isinstance(content, str):
                anthropic_content = content
            elif isinstance(content, list):
                anthropic_content = []
                for part in content:
                    part_type = part.get("type", "text")
                    if part_type == "text":
                        anthropic_content.append(
                            {"type": "text", "text": part.get("text", "")}
                        )
                    elif part_type == "image_url":
                        # Convert OpenAI image format to Anthropic format
                        image_url = part.get("image_url", {})
                        url = (
                            image_url.get("url", "")
                            if isinstance(image_url, dict)
                            else image_url
                        )
                        if url.startswith("data:"):
                            # Base64 encoded image
                            # Format: data:image/jpeg;base64,<data>
                            try:
                                media_type_part, data = url.split(";base64,", 1)
                                media_type = media_type_part.split(":", 1)[1]
                                anthropic_content.append(
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": media_type,
                                            "data": data,
                                        },
                                    }
                                )
                            except (ValueError, IndexError):
                                # If parsing fails, skip the image
                                pass
                        else:
                            # URL-based image
                            anthropic_content.append(
                                {
                                    "type": "image",
                                    "source": {"type": "url", "url": url},
                                }
                            )
                    elif part_type == "image":
                        # Already in Anthropic format
                        anthropic_content.append(part)
            else:
                anthropic_content = str(content) if content else ""

            # Map assistant role
            anthropic_role = "assistant" if role == "assistant" else "user"
            anthropic_messages.append(
                {"role": anthropic_role, "content": anthropic_content}
            )

        return anthropic_messages, system_prompt

    def _convert_tools(self, tools: list) -> list:
        """Convert OpenAI-style tools to Anthropic format."""
        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                anthropic_tools.append(
                    {
                        "name": func.get("name", ""),
                        "description": func.get("description", ""),
                        "input_schema": func.get("parameters", {}),
                    }
                )
            else:
                # Already in Anthropic format or unknown format—pass through
                anthropic_tools.append(tool)
        return anthropic_tools

    def _non_stream_response(self, url: str, headers: dict, payload: dict) -> str:
        """Handle non-streaming API requests."""
        try:
            payload["stream"] = False
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.valves.REQUEST_TIMEOUT,
            )
            response.raise_for_status()

            res = response.json()

            # Check for Anthropic error format
            if res.get("type") == "error":
                error_msg = res.get("error", {}).get("message", "Unknown error")
                return f"Proxy Error: {error_msg}"

            # Extract content from Anthropic response format
            content_blocks = res.get("content", [])
            result = ""

            for block in content_blocks:
                block_type = block.get("type", "")
                if block_type == "thinking":
                    thinking_text = block.get("thinking", "")
                    if thinking_text:
                        result += f"<think>\n{thinking_text}\n</think>\n\n"
                elif block_type == "text":
                    result += block.get("text", "")
                elif block_type == "tool_use":
                    # Format tool use for OpenWebUI display
                    tool_name = block.get("name", "unknown")
                    tool_input = json.dumps(block.get("input", {}), indent=2)
                    result += f"\n\n**Tool Call: {tool_name}**\n```json\n{tool_input}\n```\n"

            return result if result else ""

        except requests.exceptions.Timeout:
            return f"Pipe Error: Request timed out ({self.valves.REQUEST_TIMEOUT}s)"
        except requests.exceptions.HTTPError as e:
            error_msg = f"Pipe Error: HTTP {e.response.status_code}"
            try:
                detail = e.response.json().get("error", {}).get("message", "")
                if detail:
                    error_msg += f": {detail}"
            except (json.JSONDecodeError, AttributeError):
                pass
            return error_msg
        except Exception as e:
            traceback.print_exc()
            return f"Pipe Error: {e}"

    def _stream_response(
        self, url: str, headers: dict, payload: dict
    ) -> Generator[str, None, None]:
        """Handle streaming API requests using SSE from the Anthropic proxy."""
        response = None
        try:
            payload["stream"] = True
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=self.valves.STREAM_TIMEOUT,
            )
            response.raise_for_status()

            in_thinking = False
            thinking_started = False

            for line in response.iter_lines():
                if not line:
                    continue

                line_str = line.decode("utf-8") if isinstance(line, bytes) else line

                # Skip event type lines — we only care about data lines
                if line_str.startswith("event:"):
                    continue

                if not line_str.startswith("data: "):
                    continue

                data = line_str[len("data: "):]
                if data == "[DONE]":
                    break

                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")

                # Handle Anthropic SSE event types
                if event_type == "content_block_start":
                    block = event.get("content_block", {})
                    block_type = block.get("type", "")

                    if block_type == "thinking":
                        in_thinking = True
                        thinking_started = True
                        yield "<think>\n"
                    elif block_type == "text":
                        if in_thinking:
                            in_thinking = False
                            yield "\n</think>\n\n"

                elif event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    delta_type = delta.get("type", "")

                    if delta_type == "thinking_delta":
                        thinking_text = delta.get("thinking", "")
                        if thinking_text:
                            yield thinking_text
                    elif delta_type == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            yield text

                elif event_type == "content_block_stop":
                    # If we were in thinking mode and the block stopped,
                    # close the thinking tag
                    if in_thinking:
                        in_thinking = False
                        yield "\n</think>\n\n"

                elif event_type == "message_stop":
                    break

                elif event_type == "error":
                    error_msg = event.get("error", {}).get("message", "Unknown error")
                    yield f"\n\nProxy Error: {error_msg}"
                    break

        except requests.exceptions.Timeout:
            yield f"\n\nPipe Error: Stream timed out ({self.valves.STREAM_TIMEOUT}s)"
        except requests.exceptions.HTTPError as e:
            error_msg = f"Pipe Error: HTTP {e.response.status_code}"
            try:
                detail = e.response.json().get("error", {}).get("message", "")
                if detail:
                    error_msg += f": {detail}"
            except (json.JSONDecodeError, AttributeError):
                pass
            yield error_msg
        except requests.exceptions.ConnectionError:
            yield "\n\nPipe Error: Lost connection to Antigravity Proxy"
        except Exception as e:
            traceback.print_exc()
            yield f"\n\nPipe Error: {e}"
        finally:
            if response:
                response.close()
