"""OpenRouter client: the model list and one streaming call.

Originally written by Tejas Katira in chats_router.py (see git history). Kept as the single
place that knows the provider, so swapping it (ARCHITECTURE.md §10) touches only this file:
base URL, key and model ids all come from here.
"""

import json
import os
from typing import AsyncIterator

import httpx
from fastapi import HTTPException
from pydantic import BaseModel

OPENROUTER_URL = os.getenv("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")


class AvailableModel(BaseModel):
    id: str
    name: str
    description: str
    supports_images: bool
    context_length: int


AVAILABLE_MODELS: list[AvailableModel] = [
    AvailableModel(
        id="nvidia/nemotron-3-ultra-550b-a55b:free",
        name="Nemotron 3 Ultra",
        description="Large text model with a 1M-token context window (best)",
        supports_images=False,
        context_length=1_000_000,
    ),
    AvailableModel(
        id="nvidia/nemotron-3.5-super-vl:free",
        name="Nemotron 3.5 Super VL",
        description="General-purpose model that allow inputs of text, images, and video with a 1M-token context window",
        supports_images=True,
        context_length=1_000_000,
    ),
    AvailableModel(
        id="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        name="Nemotron 3 Nano Omni",
        description="Model that accepts text, image, video, and audio inputs with 256K-token context window",
        supports_images=True,
        context_length=256_000,
    ),
]

DEFAULT_MODEL_ID = AVAILABLE_MODELS[0].id
_MODELS_BY_ID = {m.id: m for m in AVAILABLE_MODELS}


def get_model_or_400(model_id: str) -> AvailableModel:
    model = _MODELS_BY_ID.get(model_id)
    if model is None:
        raise HTTPException(400, f"Unknown model: {model_id}")
    return model


async def stream_openrouter(
    messages: list[dict],
    model: str,
    transport: httpx.AsyncBaseTransport | None = None,
    tools: list[dict] | None = None,
    tool_choice: str | None = None,
) -> AsyncIterator[dict]:
    """Yield {"text": str} per token, then {"usage": {...}, "model": str} if the provider sent
    usage, or a single {"error": ...} and stop. `transport` exists so tests can fake the provider.
    With `tools`, a reply that calls tools also yields {"tool_calls": [...]} (OpenAI format) before usage."""
    headers = {"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"}
    body = {"model": model, "messages": messages, "stream": True}
    if tools:
        body["tools"] = tools
    if tool_choice:
        body["tool_choice"] = tool_choice
    final_model = model
    usage = None
    calls: dict[int, dict] = {}  # tool calls arrive as fragments, keyed by index

    async with httpx.AsyncClient(timeout=120, transport=transport) as client:
        async with client.stream("POST", OPENROUTER_URL, json=body, headers=headers) as r:
            if r.status_code != 200:
                yield {"error": (await r.aread()).decode()}
                return

            async for line in r.aiter_lines():
                if not line.startswith("data: "):
                    continue  # keep-alive comments and blank lines

                payload = line[len("data: "):]
                if payload == "[DONE]":
                    break

                chunk = json.loads(payload)
                if chunk.get("error"):
                    yield {"error": chunk["error"]}
                    return

                final_model = chunk.get("model", final_model)
                choices = chunk.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    text = delta.get("content")
                    if text:
                        yield {"text": text}
                    for tc in delta.get("tool_calls") or []:
                        call = calls.setdefault(
                            tc.get("index", 0), {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                        )
                        call["id"] = tc.get("id") or call["id"]
                        fn = tc.get("function") or {}
                        call["function"]["name"] += fn.get("name") or ""
                        call["function"]["arguments"] += fn.get("arguments") or ""
                if chunk.get("usage"):
                    usage = chunk["usage"]

    if calls:
        yield {"tool_calls": [calls[i] for i in sorted(calls)]}
    if usage:
        yield {"usage": usage, "model": final_model}
