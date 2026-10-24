from __future__ import annotations

import asyncio
import json
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

import httpx
from pydantic import ValidationError

from . import prompts
from .deps import AgentContext, JudgeView
from .streaming import FieldTap
from .schemas import (
    AgentAction,
    AskAction,
    Claim,
    FinishAction,
    FrameResult,
    JudgeVerdict,
    Question,
    SearchAction,
    TurnOutput,
    Usage,
)

RETRY_STATUS = {408, 429, 500, 502, 503, 504}
MAX_TOKENS_CAP = 16000  # a retry after a length cut-off doubles max_tokens up to this
EXPLICIT_CACHE_PREFIXES = ("anthropic/", "google/")


class BrainError(Exception):
    def __init__(self, code: str, message: str = "", usage: Optional["Usage"] = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.usage = usage  # what the failed attempts already cost, so it is still counted

SKIPPED_TURN = "(This side's turn could not be produced: the model returned an invalid reply.)"

# A quote ends a JSON string only if what follows is JSON structure; otherwise it is a quote inside the text.
_AFTER_STRING_END = re.compile(r'\s*(?:$|[}\]:]|,\s*(?:["{\[\-\d]|true\b|false\b|null\b))')


def _escape_inner_quotes(raw: str) -> str:
    out: list[str] = []
    i, n, in_str = 0, len(raw), False
    while i < n:
        ch = raw[i]
        if not in_str:
            in_str = ch == '"'
            out.append(ch)
        elif ch == "\\" and i + 1 < n:
            out.append(raw[i:i + 2])
            i += 2
            continue
        elif ch == '"':
            if _AFTER_STRING_END.match(raw, i + 1):
                in_str = False
                out.append(ch)
            else:
                out.append('\\"')
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def lenient_loads(raw: str) -> Any:
    """Models sometimes put a raw double quote inside a text value ('says "no silver bullet" and...'), which breaks strict
    JSON. Try strict first, then escape the quotes that cannot be string ends. Still raises ValueError if it cannot parse."""
    try:
        return json.loads(raw, strict=False)
    except ValueError:
        return json.loads(_escape_inner_quotes(raw), strict=False)


@dataclass
class ChatResult:
    id: str
    message: dict[str, Any]
    usage: Usage
    finish_reason: str


def parse_usage(body: dict[str, Any], model: str, latency_ms: int) -> Usage:
    u = body.get("usage") or {}
    return Usage(
        model=body.get("model") or model,
        prompt_tokens=int(u.get("prompt_tokens") or 0),
        completion_tokens=int(u.get("completion_tokens") or 0),
        reasoning_tokens=int((u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0),
        cached_tokens=int((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0),
        cost=float(u.get("cost") or 0.0),
        latency_ms=latency_ms,
        generation_id=str(body.get("id") or ""),
    )


def merge_usage(a: Optional[Usage], b: Usage) -> Usage:
    if a is None:
        return b
    return a.model_copy(
        update={
            "prompt_tokens": a.prompt_tokens + b.prompt_tokens,
            "completion_tokens": a.completion_tokens + b.completion_tokens,
            "reasoning_tokens": a.reasoning_tokens + b.reasoning_tokens,
            "cached_tokens": a.cached_tokens + b.cached_tokens,
            "cost": a.cost + b.cost,
            "latency_ms": a.latency_ms + b.latency_ms,
            "generation_id": b.generation_id or a.generation_id,
            "attempts": a.attempts + b.attempts,
        }
    )


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://openrouter.ai/api/v1",
        http: Optional[httpx.AsyncClient] = None,
        app_url: str = "",
        app_title: str = "Tangent",
        max_retries: int = 3,
        data_collection: str = "deny",
        reasoning_effort: Optional[str] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        timeout: float = 120.0,
    ) -> None:
        self._key = api_key
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._http = http or httpx.AsyncClient(timeout=timeout)
        self._headers = {"Authorization": f"Bearer {api_key}", "X-Title": app_title}
        if app_url:
            self._headers["HTTP-Referer"] = app_url
        self._max_retries = max_retries
        self._provider = {"require_parameters": True, "data_collection": data_collection}
        # "low" | "medium" | "high"; None leaves each model's default. Reasoning tokens are billed and count against max_tokens.
        self._reasoning = {"effort": reasoning_effort} if reasoning_effort else None
        self._sleep = sleep

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        response_format: Optional[dict[str, Any]] = None,
        temperature: Optional[float] = None,
        max_tokens: int = 3000,
        tap: Optional[Any] = None,
    ) -> ChatResult:
        """tap (a streaming.FieldTap) switches the request to stream=true: the text of one JSON field is passed to the tap
        as it arrives, and the assembled reply is returned exactly like a normal one (same retries, same usage)."""
        # temperature is omitted unless given: with require_parameters=true, models that reject it
        # (Haiku 5.5, GPT-6 Luna) would have every endpoint filtered out and return 404.
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "provider": self._provider,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if self._reasoning:
            body["reasoning"] = self._reasoning
        if tools:
            body["tools"] = tools
            # "required" is rejected by Haiku 5.5 routing; "auto" works and a missing call goes through the repair retry.
            body["tool_choice"] = tool_choice or "auto"
        if response_format:
            body["response_format"] = response_format

        last = ""
        for attempt in range(self._max_retries + 1):
            t0 = time.monotonic()
            if tap is not None:
                try:
                    got = await self._stream_once(body, model, tap, t0)
                except httpx.TransportError as e:
                    got = f"transport: {type(e).__name__}"
                if isinstance(got, str):
                    last = got
                    await self._backoff(attempt)
                    continue
                return got
            try:
                resp = await self._http.post(self._url, json=body, headers=self._headers)
            except httpx.TransportError as e:
                last = f"transport: {type(e).__name__}"
                await self._backoff(attempt)
                continue
            latency = int((time.monotonic() - t0) * 1000)
            if resp.status_code == 401:
                raise BrainError("openrouter_auth", "invalid API key")
            if resp.status_code == 402:
                raise BrainError("openrouter_credits", "insufficient credits")
            if resp.status_code in RETRY_STATUS:
                last = f"http {resp.status_code}"
                await self._backoff(attempt)
                continue
            if resp.status_code >= 400:
                raise BrainError("openrouter_rejected", f"http {resp.status_code}: {resp.text[:1500]}")
            try:
                data = resp.json()
            except ValueError:
                last = "non-json response"
                await self._backoff(attempt)
                continue
            err = data.get("error")
            if err:
                code = err.get("code")
                if isinstance(code, int) and code in RETRY_STATUS:
                    last = f"upstream {code}"
                    await self._backoff(attempt)
                    continue
                raise BrainError("openrouter_error", str(err)[:300])
            choices = data.get("choices") or []
            if not choices:
                last = "empty choices"
                await self._backoff(attempt)
                continue
            ch = choices[0]
            return ChatResult(
                id=str(data.get("id") or ""),
                message=ch.get("message") or {},
                usage=parse_usage(data, model, latency),
                finish_reason=str(ch.get("finish_reason") or ""),
            )
        raise BrainError("openrouter_unavailable", last)

    async def _stream_once(self, body: dict[str, Any], model: str, tap: Any, t0: float) -> "ChatResult | str":
        """One streamed attempt. Returns the ChatResult, or a short reason string when the attempt should be retried.
        Raises BrainError for failures a retry cannot fix (bad key, no credits, rejected request)."""
        await tap.start()  # a retry begins here too, so text from the failed attempt is cleared on the client
        content: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        tapped: Optional[int] = None
        usage_body: dict[str, Any] = {}
        finish, rid, served = "", "", ""
        saw_done = False
        async with self._http.stream("POST", self._url, json={**body, "stream": True}, headers=self._headers) as resp:
            if resp.status_code != 200:
                text = (await resp.aread()).decode("utf-8", "replace")
                if resp.status_code == 401:
                    raise BrainError("openrouter_auth", "invalid API key")
                if resp.status_code == 402:
                    raise BrainError("openrouter_credits", "insufficient credits")
                if resp.status_code in RETRY_STATUS:
                    return f"http {resp.status_code}"
                raise BrainError("openrouter_rejected", f"http {resp.status_code}: {text[:1500]}")
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue  # blank lines and ": OPENROUTER PROCESSING" keep-alives
                data = line[5:].strip()
                if data == "[DONE]":
                    saw_done = True
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                err = chunk.get("error")
                if err:
                    code = err.get("code") if isinstance(err, dict) else None
                    if isinstance(code, int) and code in RETRY_STATUS:
                        return f"upstream {code}"
                    raise BrainError("openrouter_error", str(err)[:300])
                rid = str(chunk.get("id") or rid)
                served = str(chunk.get("model") or served)
                if chunk.get("usage"):
                    usage_body = chunk["usage"]
                for ch in chunk.get("choices") or []:
                    delta = ch.get("delta") or {}
                    if ch.get("finish_reason"):
                        finish = str(ch["finish_reason"])
                    piece = delta.get("content")
                    if piece:
                        content.append(piece)
                        if tap.source == "content":
                            await tap.feed(piece)
                    for tc in delta.get("tool_calls") or []:
                        idx = int(tc.get("index") or 0)
                        slot = calls.setdefault(idx, {"id": "", "name": "", "args": []})
                        fn = tc.get("function") or {}
                        if tc.get("id"):
                            slot["id"] = tc["id"]
                        if fn.get("name"):
                            slot["name"] = fn["name"]
                        frag = fn.get("arguments")
                        if frag:
                            slot["args"].append(frag)
                            if tap.source == "tool":
                                tapped = idx if tapped is None else tapped
                                if idx == tapped:
                                    await tap.feed(frag)
        if not content and not calls:
            return "empty stream"
        if not (finish or saw_done):
            return "stream ended early"
        message: dict[str, Any] = {"role": "assistant", "content": "".join(content) or None}
        if calls:
            message["tool_calls"] = [
                {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": "".join(c["args"]) or "{}"}}
                for _, c in sorted(calls.items())
            ]
        latency = int((time.monotonic() - t0) * 1000)
        return ChatResult(
            id=rid,
            message=message,
            usage=parse_usage({"usage": usage_body, "id": rid, "model": served}, model, latency),
            finish_reason=finish,
        )

    async def _backoff(self, attempt: int) -> None:
        if attempt < self._max_retries:
            await self._sleep(min(8.0, 2**attempt) * (0.5 + random.random() / 2))


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


_THINK = {"type": "string", "description": "One or two sentences on why you are doing this. The user reads it."}
_EVIDENCE_IDS = {"type": "array", "items": {"type": "string"}, "description": "Evidence ids from <evidence> only."}


def agent_tools(ctx: AgentContext) -> list[dict[str, Any]]:
    tools = []
    if ctx.may_search and not ctx.force_finish:
        tools.append(
            _tool(
                "search_papers",
                "Search research papers. Results become citable evidence.",
                {
                    "query": {"type": "string"},
                    "more_queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": max(0, min(ctx.searches_left, ctx.batch_max) - 1),
                        "description": "Optional further queries for different angles. They run together with `query` in one step; "
                        "each one uses up one of your searches.",
                    },
                    "thinking": _THINK,
                },
                ["query", "thinking"],
            )
        )
    if ctx.may_ask and not ctx.force_finish:
        tools.append(
            _tool(
                "ask_user",
                "Ask the user 1-3 multiple-choice questions when their answer would change your argument.",
                {
                    "thinking": _THINK,
                    "questions": {
                        "type": "array",
                        "maxItems": 3,
                        "items": {
                            "type": "object",
                            "properties": {
                                "prompt": {"type": "string"},
                                "type": {"type": "string", "enum": ["single", "multi"]},
                                "options": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {"label": {"type": "string"}, "description": {"type": "string"}},
                                        "required": ["label"],
                                    },
                                },
                            },
                            "required": ["prompt", "options"],
                        },
                    },
                },
                ["questions", "thinking"],
            )
        )
    props: dict[str, Any] = {
        "thinking": {"type": "array", "items": {"type": "string"}, "description": "1-4 short working notes. The user reads them."},
        "argument": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "evidence_ids": _EVIDENCE_IDS},
                "required": ["text"],
            },
        },
    }
    tools.append(_tool("submit_turn", "Finish this turn.", props, ["thinking", "argument", "claims"]))
    return tools


def _args(call: dict[str, Any]) -> dict[str, Any]:
    raw = (call.get("function") or {}).get("arguments") or "{}"
    val = lenient_loads(raw) if isinstance(raw, str) else raw
    if not isinstance(val, dict):
        raise ValueError("arguments must be an object")
    return val


def parse_action(ctx: AgentContext, message: dict[str, Any]) -> AgentAction:
    calls = message.get("tool_calls") or []
    if not calls:
        raise ValueError("no tool call in reply")
    call = calls[0]
    name = (call.get("function") or {}).get("name")
    offered = {t["function"]["name"] for t in agent_tools(ctx)}
    if name not in offered:
        raise ValueError(f"tool {name!r} is not available now; available: {sorted(offered)}")
    a = _args(call)
    if name == "search_papers":
        more = a.get("more_queries") or []
        more = [str(q).strip() for q in more if isinstance(q, str) and q.strip()] if isinstance(more, list) else []
        return SearchAction(query=str(a["query"]).strip(), more_queries=more, thinking=str(a.get("thinking", "")))
    if name == "ask_user":
        qs = [
            Question(
                prompt=q["prompt"],
                type=q.get("type", "single"),
                options=[{"label": o["label"], "description": o.get("description", "")} for o in q.get("options", [])],
            )
            for q in a["questions"][:3]
        ]
        if not qs:
            raise ValueError("ask_user needs at least one question")
        return AskAction(questions=qs, thinking=str(a.get("thinking", "")))
    claims = [
        Claim(
            id=f"{ctx.side}-{ctx.phase}-{ctx.round}-{i}",
            text=c["text"],
            evidence_ids=[str(e) for e in c.get("evidence_ids", [])],
        )
        for i, c in enumerate(a["claims"], 1)
    ]
    thinking = a["thinking"] if isinstance(a["thinking"], list) else [str(a["thinking"])]
    return FinishAction(
        turn=TurnOutput(
            thinking=[str(t) for t in thinking][:6],
            argument=str(a["argument"]),
            claims=claims,
        )
    )


FRAME_SCHEMA = {
    "type": "object",
    "properties": {
        "proposition": {"type": "string"},
        "for_brief": {"type": "string"},
        "against_brief": {"type": "string"},
        # Written before the questions on purpose; code, not the model, decides whether the questions are shown (debate/framing.py).
        "criterion_stated": {"type": "boolean"},
        "setting_stated": {"type": "boolean"},
        "context_resolves": {"type": "boolean"},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["prompt", "options"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["proposition", "for_brief", "against_brief", "criterion_stated", "setting_stated", "context_resolves", "questions"],
    "additionalProperties": False,
}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        # Property order matters: the model writes them in this order, so the scores come before the prose that explains them.
        "claim_checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string", "description": "claim id as shown in the transcript, e.g. A1 or B2"},
                    "label": {"type": "string", "enum": ["supported", "partly_supported", "unsupported", "uncited"]},
                    "reason": {"type": "string", "description": "at most 20 words"},
                },
                "required": ["claim", "label", "reason"],
                "additionalProperties": False,
            },
        },
        "criteria": {
            "type": "array",
            "description": "one entry for Position A and one for Position B",
            "items": {
                "type": "object",
                "properties": {
                    "position": {"type": "string", "enum": ["A", "B"]},
                    "scope": {"type": "integer", "description": "0 to 10"},
                    "engagement": {"type": "integer", "description": "0 to 10"},
                    "fidelity": {"type": "integer", "description": "0 to 10"},
                    "note": {"type": "string"},
                },
                "required": ["position", "scope", "engagement", "fidelity", "note"],
                "additionalProperties": False,
            },
        },
        "leaning": {"type": "string", "enum": ["A", "B", "none"]},
        "rationale": {"type": "string"},
        "summary": {"type": "string"},
        "final_output": {"type": "string"},
        "strongest_counterpoints": {"type": "array", "items": {"type": "string"}},
        "verdict_flips_if": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "claim_checks", "criteria", "leaning", "rationale", "summary", "final_output",
        "strongest_counterpoints", "verdict_flips_if",
    ],
    "additionalProperties": False,
}


def _json_format(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}


class OpenRouterBrain:
    def __init__(
        self,
        client: OpenRouterClient,
        *,
        for_model: str,
        against_model: str,
        judge_model: str,
        frame_model: Optional[str] = None,
        max_repairs: int = 2,
        agent_max_tokens: int = 6000,
        judge_max_tokens: int = 6000,
    ) -> None:
        self.client = client
        self.models = {"for": for_model, "against": against_model}
        self.judge_model = judge_model
        self.frame_model = frame_model or judge_model
        self.max_repairs = max_repairs
        self.agent_max_tokens = agent_max_tokens
        self.judge_max_tokens = judge_max_tokens

    async def _structured(
        self, model: str, system: str, user: Any, parse: Callable[[ChatResult], Any], **chat: Any
    ) -> tuple[Any, Usage]:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        usage: Optional[Usage] = None
        problem = detail = ""
        for attempt in range(self.max_repairs + 1):
            msgs = messages if not problem else messages + [
                {"role": "user", "content": f"Your previous reply was invalid ({problem}). Reply again, correctly. If tools are provided, respond by calling exactly one of them. "
                 "Never put a raw double quote inside a text value: quote phrases with single quotes."}
            ]
            res = await self.client.chat(model=model, messages=msgs, **chat)
            usage = merge_usage(usage, res.usage)
            try:
                return parse(res), usage
            except (ValueError, KeyError, TypeError, ValidationError) as e:
                problem = str(e)[:200]
                detail = (f"finish_reason={res.finish_reason or '?'}, completion_tokens={res.usage.completion_tokens}, "
                          f"reasoning_tokens={res.usage.reasoning_tokens}, max_tokens={chat.get('max_tokens')}")
                if res.finish_reason == "length":
                    # Cut off at the token limit (reasoning tokens count against it). Retrying with the same limit fails the same way.
                    problem = "your reply was cut off at the length limit, so keep your notes and argument shorter; " + problem
                    chat = {**chat, "max_tokens": min(int(chat.get("max_tokens") or 3000) * 2, MAX_TOKENS_CAP)}
        raise BrainError("model_output_invalid", f"{model}: {problem} [{detail}]", usage=usage)

    @staticmethod
    def _debater_content(model: str, ctx: AgentContext) -> Any:
        """Anthropic and Gemini need an explicit breakpoint to cache a prefix; the others cache automatically. The
        breakpoint sits after the project context and proposition, which are identical across both debaters and every call."""
        if not model.startswith(EXPLICIT_CACHE_PREFIXES):
            return prompts.debater_user(ctx)
        stable, dynamic = prompts.debater_user_parts(ctx)
        return [
            {"type": "text", "text": stable, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": dynamic},
        ]

    async def step(self, ctx: AgentContext, sink: Optional[Any] = None) -> AgentAction:
        model = self.models[ctx.side]
        extra = {"tap": FieldTap("argument", sink, "tool")} if sink is not None else {}
        try:
            action, usage = await self._structured(
                model,
                prompts.debater_system(ctx),
                self._debater_content(model, ctx),
                lambda r: parse_action(ctx, r.message),
                tools=agent_tools(ctx),
                tool_choice="auto",
                max_tokens=self.agent_max_tokens,
                **extra,
            )
        except BrainError as e:
            if e.code != "model_output_invalid":
                raise
            # One unparseable reply must not kill a two-minute debate: skip this turn, say so, and let the judge see it.
            skipped = FinishAction(turn=TurnOutput(
                argument=SKIPPED_TURN,
                thinking=[f"The model returned an invalid reply {self.max_repairs + 1} times, so this turn was skipped. ({str(e)[-260:]})"]))
            return skipped.model_copy(update={"usage": e.usage})
        return action.model_copy(update={"usage": usage})

    async def frame(self, topic: str, context: str) -> FrameResult:
        def parse(r: ChatResult) -> FrameResult:
            d = lenient_loads(r.message.get("content") or "")
            return FrameResult(
                proposition=d["proposition"],
                side_briefs={"for": d["for_brief"], "against": d["against_brief"]},
                questions=[Question(prompt=q["prompt"], options=[{"label": o} for o in q["options"]]) for q in d["questions"][:3]],
                checks={k: bool(d.get(k, False)) for k in ("criterion_stated", "setting_stated", "context_resolves")},
            )

        out, usage = await self._structured(
            self.frame_model,
            prompts.FRAME_SYSTEM,
            prompts.frame_user(topic, context),
            parse,
            response_format=_json_format("debate_frame", FRAME_SCHEMA),
            max_tokens=3000,
        )
        return out.model_copy(update={"usage": usage})

    async def judge(self, view: JudgeView, fixed_winner: Optional[str], sink: Optional[Any] = None) -> JudgeVerdict:
        extra = {"tap": FieldTap("final_output", sink, "content")} if sink is not None else {}

        def parse(r: ChatResult) -> JudgeVerdict:
            d = lenient_loads(r.message.get("content") or "")
            leaning = d["leaning"] if d["leaning"] in ("A", "B", "none") else "none"
            # winner / confidence / scores are placeholders: graph.judge replaces them with debate.scoring's result.
            return JudgeVerdict(
                winner=leaning,
                would_have_chosen=leaning,
                confidence=0.0,
                rationale=d["rationale"],
                summary=d["summary"],
                final_output=d["final_output"],
                scores={},
                strongest_counterpoints=[str(x) for x in d["strongest_counterpoints"]],
                verdict_flips_if=[str(x) for x in d["verdict_flips_if"]],
                rubric={"claim_checks": d["claim_checks"], "criteria": d["criteria"], "leaning": leaning},
            )

        out, usage = await self._structured(
            self.judge_model,
            prompts.judge_system(fixed_winner),
            prompts.judge_user(view),
            parse,
            response_format=_json_format("debate_verdict", JUDGE_SCHEMA),
            max_tokens=self.judge_max_tokens,
            **extra,
        )
        return out.model_copy(update={"usage": usage})