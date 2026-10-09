from dotenv import load_dotenv

load_dotenv()

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.routers import (
    auth_router,
    workspace_router,
    projects_router,
    shares_router,
    nodes_router,
    chats_router,
)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Tangent")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

production_origin = os.getenv("FRONTEND_URL")
if production_origin:
    origins.append(production_origin.rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(workspace_router.router)
app.include_router(projects_router.router)
app.include_router(shares_router.router)
app.include_router(nodes_router.router)
