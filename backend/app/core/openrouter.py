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


AVAILABLE_MODELS: list[AvailableModel] = [
    AvailableModel(
        id="nvidia/nemotron-3-ultra-550b-a55b:free",
        name="Nemotron 3 Ultra",
        description="Large text model with a 1M-token context window (best)",
        supports_images=False,
    ),
    AvailableModel(
        id="nvidia/nemotron-3.5-super-vl:free",
        name="Nemotron 3.5 Super VL",
        description="General-purpose model that allow inputs of text, images, and video with a 1M-token context window",
        supports_images=True,
    ),
    AvailableModel(
        id="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        name="Nemotron 3 Nano Omni",
        description="Model that accepts text, image, video, and audio inputs with 300K context length",
        supports_images=True,
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
) -> AsyncIterator[dict]:
    """Yield {"text": str} per token, then {"usage": {...}, "model": str} if the provider sent
    usage, or a single {"error": ...} and stop. `transport` exists so tests can fake the provider."""
    headers = {"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"}
    body = {"model": model, "messages": messages, "stream": True}
    final_model = model
    usage = None

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
                    text = choices[0].get("delta", {}).get("content")
                    if text:
                        yield {"text": text}
                if chunk.get("usage"):
                    usage = chunk["usage"]

    if usage:
        yield {"usage": usage, "model": final_model}
