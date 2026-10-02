import os
import httpx
from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

router = APIRouter()

class PromptRequest(BaseModel):
    prompt: str
    model: str = "openrouter/free"

class ModelResponse(BaseModel):
    model: str
    output: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

saved_calls: list[ModelResponse] = []

@router.post("/model_call", response_model=ModelResponse)
async def model_call(req: PromptRequest):
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