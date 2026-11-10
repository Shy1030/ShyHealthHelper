from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import __version__
from .ai_store import apply_saved_ai_settings
from .config import settings
from .db import init_db
from .routers import ai, body, chat, cycle, diet, exercise, finance, home, profile, xiaomi

settings.ensure_dirs()
apply_saved_ai_settings()
init_db()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_dirs()
    init_db()
    yield


app = FastAPI(
    title="ShyHealthHelper",
    description="月经记录与预测、饮食营养估算、运动建议、微信记账联动的个人健康助手",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile.router)
app.include_router(cycle.router)
app.include_router(diet.router)
app.include_router(exercise.router)
app.include_router(body.router)
app.include_router(xiaomi.router)
app.include_router(home.router)
app.include_router(chat.router)
app.include_router(ai.router)
app.include_router(finance.router)


@app.get("/api/health", tags=["system"])
def health() -> dict:
    return {
        "status": "ok",
        "app": "ShyHealthHelper",
        "version": __version__,
        "ai_mode": settings.ai_mode,
        "mock_mode": settings.mock_mode,
        "model": settings.deepseek_model,
        "vision_model": settings.deepseek_vision_model,
    }


app.mount(
    "/uploads",
    StaticFiles(directory=str(settings.upload_dir)),
    name="uploads",
)
app.mount("/", StaticFiles(directory=str(settings.web_dir), html=True), name="web")
