import os
import httpx
import json
import base64
from fastapi import (
    APIRouter, 
    HTTPException, 
    File, 
    Form, 
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB

router = APIRouter()


# ---------- Model list ----------

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
        id="google/gemma-4-31b-it:free",
        name="Gemma 4 31B",
        description="General-purpose model that allow inputs of images, video, and audio with a 256K token context window",
        supports_images=True,
    ),
    AvailableModel(
        id="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        name="Nemotron 3 Nano Omni",
        description="Model that accepts text, image, video, and audio inputs with 300K context length",
        supports_images=True,
    ),
    AvailableModel(
        id="nvidia/nemotron-3.5-lightning:free",
        name="Nemotron 3.5 Lightning",
        description="Fast text model for coding and structured output - 1M context",
        supports_images=False,
    ),
]

DEFAULT_MODEL_ID = AVAILABLE_MODELS[0].id
MODELS_BY_ID = {m.id: m for m in AVAILABLE_MODELS}


def get_model_or_400(model_id: str) -> AvailableModel:
    model = MODELS_BY_ID.get(model_id)
    if model is None:
        raise HTTPException(400, f"Unknown model: {model_id}")
    return model


# ---------- Request / response shapes ----------

class PromptRequest(BaseModel):
    prompt: str
    model: str = DEFAULT_MODEL_ID

class ModelResponse(BaseModel):
    model: str
    output: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

saved_calls: list[ModelResponse] = []


# ---------- OpenRouter request body (works with raw bytes) ----------

def build_body(
    prompt: str,
    model: str,
    file_bytes: bytes | None = None,
    content_type: str | None = None,
    filename: str | None = None,
) -> dict:
    model_info = get_model_or_400(model)
    content = [{"type": "text", "text": prompt}]
    body = {"model": model, "stream": True}

    if file_bytes:
        if len(file_bytes) > MAX_FILE_BYTES:
            raise HTTPException(413, "File too large (10 MB max)")

        encoded = base64.b64encode(file_bytes).decode("utf-8")
        data_url = f"data:{content_type};base64,{encoded}"

        if content_type and content_type.startswith("image/"):
            if not model_info.supports_images:
                raise HTTPException(400, f"{model_info.name} can't read images")
            content.append({"type": "image_url", "image_url": {"url": data_url}})
        elif content_type == "application/pdf":
            content.append(
                {"type": "file", "file": {"filename": filename, "file_data": data_url}}
            )
            # Free text-extraction engine, so no paid OCR charges
            body["plugins"] = [{"id": "file-parser", "pdf": {"engine": "pdf-text"}}]
        else:
            raise HTTPException(400, "Only images and PDFs are supported")

    body["messages"] = [{"role": "user", "content": content}]
    return body


# ---------- Shared streaming generator ----------

async def stream_openrouter(body: dict):
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    full_text = []
    final_model = body["model"]
    usage = None

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST", OPENROUTER_URL, json=body, headers=headers
        ) as r:
            if r.status_code != 200:
                error_text = (await r.aread()).decode()
                yield {"error": error_text}
                return

            async for line in r.aiter_lines():
                if not line.startswith("data: "):
                    continue  # skip keep-alive comments and blank lines

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
                        full_text.append(text)
                        yield {"text": text}

                if chunk.get("usage"):
                    usage = chunk["usage"]

    if usage:
        saved_calls.append(
            ModelResponse(
                model=final_model,
                output="".join(full_text),
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            )
        )
        yield {"usage": usage, "model": final_model}


# ---------- Endpoints ----------

@router.get("/models", response_model=list[AvailableModel])
async def list_models():
    return AVAILABLE_MODELS

@router.post("/model_call", response_model=ModelResponse)
async def model_call(req: PromptRequest):
    get_model_or_400(req.model)
    
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    body = {
        "model": req.model,
        "messages": [{"role": "user", "content": req.prompt}],
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(OPENROUTER_URL, json=body, headers=headers)

    if response.status_code != 200:
        raise HTTPException(response.status_code, response.text)

    data = response.json()
    usage = data["usage"]

    result = ModelResponse(
        model=data["model"],
        output=data["choices"][0]["message"]["content"],
        prompt_tokens=usage["prompt_tokens"],
        completion_tokens=usage["completion_tokens"],
        total_tokens=usage["total_tokens"],
    )

    saved_calls.append(result)
    return result

@router.post("/model_call_stream")
async def model_call_stream(
    prompt: str = Form(...),
    model: str = Form(DEFAULT_MODEL_ID),
    file: UploadFile | None = File(None),
):
    file_bytes = await file.read() if file and file.filename else None
    body = build_body(
        prompt,
        model,
        file_bytes,
        file.content_type if file else None,
        file.filename if file else None,
    )

    async def sse_events():
        async for event in stream_openrouter(body):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(sse_events(), media_type="text/event-stream")

@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            msg = await websocket.receive_json()

            try:
                file_info = msg.get("file")
                file_bytes = base64.b64decode(file_info["data"]) if file_info else None
                body = build_body(
                    msg["prompt"],
                    msg.get("model", DEFAULT_MODEL_ID),
                    file_bytes,
                    file_info["content_type"] if file_info else None,
                    file_info["filename"] if file_info else None,
                )
            except HTTPException as e:
                await websocket.send_json({"error": e.detail})
                continue
            except (KeyError, ValueError):
                await websocket.send_json({"error": "Malformed message"})
                continue

            async for event in stream_openrouter(body):
                await websocket.send_json(event)
            await websocket.send_json({"done": True})

    except WebSocketDisconnect:
        pass