from __future__ import annotations

from fastapi import APIRouter

from .. import ai_store, deepseek
from ..schemas import AISettingsUpdate

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/settings")
def get_ai_settings() -> dict:
    return ai_store.public_settings()


@router.put("/settings")
def update_ai_settings(payload: AISettingsUpdate) -> dict:
    values = payload.dict(exclude_unset=True)
    return ai_store.save_ai_settings(
        api_key=values.get("api_key"),
        base_url=values.get("base_url"),
        model=values.get("model"),
        vision_model=values.get("vision_model"),
    )


@router.delete("/settings")
def clear_ai_settings() -> dict:
    return ai_store.clear_ai_settings()


@router.post("/test")
async def test_ai_connection() -> dict:
    ok, message = await deepseek.test_connection()
    return {**ai_store.public_settings(), "ok": ok, "message": message}
