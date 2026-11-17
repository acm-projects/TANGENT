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
# OPENROUTER_FREE_MODELS=true uses the models' free variants (":free": capped at 1000 requests a day); false, the paid
# ones (billed per token, no request cap). Ids saved on cards either way still work: model_id() maps them across.
FREE_MODELS = os.getenv("OPENROUTER_FREE_MODELS", "true").strip().lower() in ("1", "true", "yes", "on")
_VARIANT = ":free" if FREE_MODELS else ""


class AvailableModel(BaseModel):
    id: str
    name: str
    description: str
    supports_images: bool
    context_length: int
    # OpenRouter's `reasoning` parameter (native thinking); per its /models supported_parameters
    supports_reasoning: bool = False


AVAILABLE_MODELS: list[AvailableModel] = [
    AvailableModel(
        id="nvidia/nemotron-3.5-lightning" + _VARIANT,
        name="Lite",
        description="Fast text model with a 1M-token context window",
        supports_images=False,
        context_length=1_000_000,
        supports_reasoning=True,
    ),
    AvailableModel(
        id="nvidia/nemotron-3.5-super-vl" + _VARIANT,
        name="Balanced",
        description="General-purpose model for text, images, and video with a 1M-token context window",
        supports_images=True,
        context_length=1_000_000,
        supports_reasoning=True,
    ),
    AvailableModel(
        id="nvidia/nemotron-3-ultra-550b-a55b" + _VARIANT,
        name="Heavy",
        description="Multimodal model for text, images, video, and audio with a 1.05M-token context window",
        supports_images=True,
        context_length=1_050_000,
        supports_reasoning=True,
    ),
]

DEFAULT_MODEL_ID = AVAILABLE_MODELS[0].id
_MODELS_BY_ID = {m.id: m for m in AVAILABLE_MODELS}
_BY_BASE = {m.id.removesuffix(":free"): m.id for m in AVAILABLE_MODELS}


def model_id(any_id: str | None) -> str | None:
    """A model id in the variant this server runs (free or paid), whichever variant it was saved as."""
    if not any_id:
        return any_id
    return _BY_BASE.get(any_id.removesuffix(":free"), any_id)


def get_model_or_400(model_id_: str) -> AvailableModel:
    model = _MODELS_BY_ID.get(model_id(model_id_))
    if model is None:
        raise HTTPException(400, f"Unknown model: {model_id_}")
    return model


async def stream_openrouter(
    messages: list[dict],
    model: str,
    transport: httpx.AsyncBaseTransport | None = None,
    tools: list[dict] | None = None,
    tool_choice: str | None = None,
    reasoning: dict | None = None,
) -> AsyncIterator[dict]:
    """Yield {"text": str} per token, then {"usage": {...}, "model": str} if the provider sent
    usage, or a single {"error": ...} and stop. `transport` exists so tests can fake the provider.
    With `tools`, a reply that calls tools also yields {"tool_calls": [...]} (OpenAI format) before usage.
    With `reasoning` (e.g. {"effort": "low"}), readable thinking streams as {"reasoning": str}, and the provider's
    structured blocks come once as {"reasoning_details": [...]}: send those back on the next turn of a tool loop."""
    headers = {"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"}
    body = {"model": model_id(model), "messages": messages, "stream": True}
    if tools:
        body["tools"] = tools
    if tool_choice:
        body["tool_choice"] = tool_choice
    if reasoning:
        body["reasoning"] = reasoning
    final_model = model
    usage = None
    calls: dict[int, dict] = {}  # tool calls arrive as fragments, keyed by index
    details: dict[int, dict] = {}  # reasoning_details too

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
                    if delta.get("reasoning"):
                        yield {"reasoning": delta["reasoning"]}
                    for i, part in enumerate(delta.get("reasoning_details") or []):
                        block = details.setdefault(part.get("index", i), {})
                        for key, value in part.items():
                            # streamed text pieces concatenate; ids, types and signatures arrive whole
                            if key in ("text", "summary", "data") and isinstance(value, str):
                                block[key] = block.get(key, "") + value
                            else:
                                block[key] = value
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

    if details:
        yield {"reasoning_details": [details[i] for i in sorted(details)]}
    if calls:
        yield {"tool_calls": [calls[i] for i in sorted(calls)]}
    if usage:
        yield {"usage": usage, "model": final_model}
