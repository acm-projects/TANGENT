from fastapi import FastAPI
from app.routers import chats_router

app = FastAPI()
app.include_router(chats_router.router)