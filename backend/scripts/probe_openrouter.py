"""Find which OpenRouter routing constraint removes every endpoint for a model.

Usage (from the backend root):
    python3 scripts/probe_openrouter.py openai/gpt-6-luna anthropic/claude-haiku-5.5

Reads OPENROUTER_DEBATE_API_KEY from the environment or .env. Never prints it.
Each variant sends one tiny request (a few tokens) so the cost is negligible.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

URL = "https://openrouter.ai/api/v1/chat/completions"
SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "probe",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
    },
}
TOOL = [{
    "type": "function",
    "function": {
        "name": "ping",
        "description": "Call this.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}]


def load_key() -> str:
    k = os.environ.get("OPENROUTER_DEBATE_API_KEY")
    if k:
        return k
    for p in (Path(".env"), Path(__file__).resolve().parent.parent / ".env"):
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("OPENROUTER_DEBATE_API_KEY="):
                    return line.split("=", 1)[1].strip().strip("\"'")
    sys.exit("OPENROUTER_DEBATE_API_KEY not found in env or .env")


PROV = {"provider": {"require_parameters": True, "data_collection": "deny"}}

VARIANTS = [
    ("plain, no provider prefs", {}, {}),
    ("data_collection=deny only", {"provider": {"data_collection": "deny"}}, {}),
    ("require_parameters only + json_schema", {"provider": {"require_parameters": True}}, {"response_format": SCHEMA}),
    ("deny + require_parameters + json_schema (frame/judge)", {"provider": {"require_parameters": True, "data_collection": "deny"}}, {"response_format": SCHEMA}),
    ("deny + require_parameters + tools (debater)", {"provider": {"require_parameters": True, "data_collection": "deny"}}, {"tools": TOOL, "tool_choice": "required"}),
    # --- the real calls also send temperature and a bigger max_tokens ---
    ("frame-like: schema + temperature=0.3 + max_tokens=1500", PROV, {"response_format": SCHEMA, "temperature": 0.3, "max_tokens": 1500}),
    ("schema + max_tokens=1500 (no temperature)", PROV, {"response_format": SCHEMA, "max_tokens": 1500}),
    ("debater-like: tools required + temperature=0.7", PROV, {"tools": TOOL, "tool_choice": "required", "temperature": 0.7}),
    ("tools tool_choice=auto (no temperature)", PROV, {"tools": TOOL, "tool_choice": "auto"}),
    ("tools tool_choice=auto + temperature=0.7", PROV, {"tools": TOOL, "tool_choice": "auto", "temperature": 0.7}),
    # --- reasoning effort (the debate sends this only if you pass --reasoning-effort / DEBATE_REASONING_EFFORT) ---
    ("reasoning effort=low + tools auto", PROV, {"tools": TOOL, "tool_choice": "auto", "reasoning": {"effort": "low"}, "max_tokens": 1500}),
    ("reasoning effort=low + json_schema", PROV, {"response_format": SCHEMA, "reasoning": {"effort": "low"}, "max_tokens": 1500}),
]


async def main(models: list[str]) -> None:
    headers = {"Authorization": f"Bearer {load_key()}"}
    async with httpx.AsyncClient(timeout=60) as http:
        for model in models:
            print(f"\n== {model}")
            for name, prov, extra in VARIANTS:
                body = {
                    "model": model,
                    "messages": [{"role": "user", "content": 'Reply with {"ok": true} or call the tool.'}],
                    "max_tokens": 50,
                    **prov,
                    **extra,
                }
                # short error: only the failed routing step, not the whole funnel
                r = await http.post(URL, json=body, headers=headers)
                if r.status_code == 200:
                    print(f"  PASS  {name}")
                else:
                    print(f"  FAIL {r.status_code}  {name}")
                    try:
                        print("        " + json.dumps(r.json().get("error", r.json()))[:1500])
                    except ValueError:
                        print("        " + r.text[:500])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1:]))