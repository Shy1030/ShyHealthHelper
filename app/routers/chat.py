from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from .. import deepseek
from ..db import get_db
from ..predictions import analyze_cycles
from ..schemas import ChatRequest
from .cycle import _load_periods
from .diet import _daily_payload

router = APIRouter(prefix="/api/chat", tags=["chat"])

HISTORY_LIMIT = 20


def _load_history(limit: int = HISTORY_LIMIT) -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT id, role, content, created_at FROM chat_messages "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    items = [dict(row) for row in rows]
    items.reverse()
    return items


def _chat_context(target_date: date) -> dict:
    _, payload = _daily_payload(target_date)
    daily = payload["summary"]
    profile = payload["profile"]
    metrics = payload["metrics"]
    cycle = analyze_cycles(_load_periods())
    return {
        "date": target_date.isoformat(),
        "weight_kg": profile.get("weight_kg"),
        "goal": profile.get("goal"),
        "bmi": metrics.get("bmi"),
        "bmr": metrics.get("bmr"),
        "tdee": metrics.get("tdee"),
        "today_diet": daily["totals"],
        "target": daily["target"],
        "remaining": daily["remaining"],
        "energy_balance": daily["energy_balance"],
        "exercise_today": daily["exercise"]["today"],
        "cycle_phase": cycle["current"]["phase"],
    }


@router.get("/messages")
def list_messages(limit: int = Query(default=100, ge=1, le=200)) -> dict:
    with get_db() as db:
        rows = db.execute(
            "SELECT id, role, content, created_at FROM chat_messages "
            "ORDER BY id ASC LIMIT ?",
            (limit,),
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


@router.post("")
async def send_message(payload: ChatRequest) -> dict:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="消息不能为空")

    target_date = date.today()
    context = _chat_context(target_date)
    history = _load_history(HISTORY_LIMIT)

    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO chat_messages (role, content) VALUES ('user', ?)",
            (message,),
        )
        user_row = db.execute(
            "SELECT id, role, content, created_at FROM chat_messages WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

    system = (
        deepseek.CHAT_SYSTEM_PROMPT
        + "\n\n用户当前数据（JSON）：\n"
        + json.dumps(context, ensure_ascii=False)
    )
    ai_messages = [
        {"role": item["role"], "content": item["content"]}
        for item in history
    ] + [{"role": "user", "content": message}]

    try:
        reply = await deepseek.chat_text(system, ai_messages, context)
    except deepseek.AIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO chat_messages (role, content) VALUES ('assistant', ?)",
            (reply,),
        )
        assistant_row = db.execute(
            "SELECT id, role, content, created_at FROM chat_messages WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

    return {
        "reply": reply,
        "messages": [dict(user_row), dict(assistant_row)],
    }


@router.delete("/messages", status_code=204)
def clear_messages() -> None:
    with get_db() as db:
        db.execute("DELETE FROM chat_messages")
