"""The OpenRouter client's stream parsing, against a faked provider (runs in CI, no secrets)."""
import asyncio
import json

import httpx

from app.core.openrouter import AVAILABLE_MODELS, stream_openrouter


def provider(chunks: list[dict], seen: list):
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, text=body)
    return httpx.MockTransport(handle)


def collect(chunks, **kwargs):
    seen = []

    async def go():
        return [e async for e in stream_openrouter([{"role": "user", "content": "q"}], "m",
                                                   transport=provider(chunks, seen), **kwargs)]
    return asyncio.run(go()), seen


def delta(**d):
    return {"choices": [{"delta": d}]}


def test_reasoning_streams_and_its_blocks_come_back_whole():
    events, seen = collect([
        delta(reasoning="weigh "), delta(reasoning_details=[{"type": "reasoning.text", "text": "weigh ", "index": 0}]),
        delta(reasoning="it"), delta(reasoning_details=[{"type": "reasoning.text", "text": "it", "index": 0,
                                                         "signature": "sig"}]),
        delta(content="Answer"),
    ], reasoning={"effort": "low"})
    assert seen[0]["reasoning"] == {"effort": "low"}
    assert [e["reasoning"] for e in events if "reasoning" in e] == ["weigh ", "it"]
    assert {"text": "Answer"} in events
    assert [e for e in events if "reasoning_details" in e] == [
        {"reasoning_details": [{"type": "reasoning.text", "text": "weigh it", "index": 0, "signature": "sig"}]}]


def test_no_reasoning_unless_asked():
    events, seen = collect([delta(content="hi")])
    assert "reasoning" not in seen[0] and events == [{"text": "hi"}]


def test_every_listed_model_can_reason():
    # checked against OpenRouter's /models supported_parameters; think() falls back for a model that can't
    assert all(m.supports_reasoning for m in AVAILABLE_MODELS)
