from __future__ import annotations

import json
from datetime import date, timedelta
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from .. import deepseek, nutrition
from ..config import settings
from ..db import get_db
from ..health_metrics import compute_metrics
from ..schemas import MealRecommendRequest
from .profile import load_profile

router = APIRouter(prefix="/api/diet", tags=["diet"])

MEAL_TYPES = {"breakfast", "lunch", "dinner", "snack"}
IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/heic": ".heic",
    "image/heif": ".heif",
}


def _serialize(row) -> dict:
    data = dict(row)
    for key in ("advice", "tips", "foods"):
        try:
            data[key] = json.loads(data.get(key) or "[]")
        except (TypeError, json.JSONDecodeError):
            data[key] = []
    data["photo_url"] = (
        f"/uploads/{data['photo_path']}" if data.get("photo_path") else None
    )
    data["vision_used"] = bool(data.get("vision_used"))
    return data


def _save_photo(photo: UploadFile, content: bytes) -> str:
    content_type = (photo.content_type or "").lower()
    extension = IMAGE_TYPES.get(content_type)
    if extension is None:
        raise HTTPException(status_code=400, detail="只支持 JPG/PNG/WebP/GIF/HEIC 图片")
    filename = f"{uuid4().hex}{extension}"
    settings.ensure_dirs()
    (settings.upload_dir / filename).write_bytes(content)
    return filename


def _delete_photo(photo_path: str | None) -> None:
    if not photo_path:
        return
    try:
        target = (settings.upload_dir / photo_path).resolve()
        if target.parent == settings.upload_dir.resolve() and target.is_file():
            target.unlink()
    except OSError:
        pass


def _load_logs(log_date: date) -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM diet_logs WHERE log_date = ? ORDER BY id ASC",
            (log_date.isoformat(),),
        ).fetchall()
    return [_serialize(row) for row in rows]


def _exercise_context(target_date: date) -> tuple[dict, dict]:
    with get_db() as db:
        today_rows = db.execute(
            "SELECT * FROM exercise_logs WHERE log_date = ? ORDER BY id ASC",
            (target_date.isoformat(),),
        ).fetchall()
        recent_start = (target_date - timedelta(days=6)).isoformat()
        recent_rows = db.execute(
            "SELECT * FROM exercise_logs WHERE log_date >= ? AND log_date <= ?",
            (recent_start, target_date.isoformat()),
        ).fetchall()

    def summarize(rows):
        items = [dict(row) for row in rows]
        by_activity: dict[str, float] = {}
        for item in items:
            name = item.get("activity") or "运动"
            by_activity[name] = by_activity.get(name, 0.0) + float(
                item.get("duration_min") or 0
            )
        estimated = [item for item in items if item.get("calories_estimated")]
        return {
            "sessions": len(items),
            "active_days": len({item.get("log_date") for item in items}),
            "duration_min": round(
                sum(float(item.get("duration_min") or 0) for item in items), 1
            ),
            "calories": round(
                sum(float(item.get("calories") or 0) for item in items), 1
            ),
            "estimated_calories": round(
                sum(float(item.get("calories") or 0) for item in estimated), 1
            ),
            "estimated_sessions": len(estimated),
            "by_activity": sorted(
                (
                    {"activity": name, "duration_min": round(minutes, 1)}
                    for name, minutes in by_activity.items()
                ),
                key=lambda item: item["duration_min"],
                reverse=True,
            )[:4],
        }

    return summarize(today_rows), summarize(recent_rows)


def _daily_payload(target_date: date) -> tuple[list[dict], dict]:
    logs = _load_logs(target_date)
    profile = load_profile()
    metrics = compute_metrics(profile)
    exercise_today, exercise_recent = _exercise_context(target_date)
    summary = nutrition.daily_summary(
        logs, profile, metrics, exercise_today, exercise_recent, target_date
    )
    summary["logs"] = logs
    return logs, {"summary": summary, "profile": profile, "metrics": metrics}


@router.get("/daily")
def daily_summary(date_: date | None = Query(default=None, alias="date")) -> dict:
    target_date = date_ or date.today()
    _, payload = _daily_payload(target_date)
    return payload["summary"]


@router.post("/recommend")
async def recommend_meal(payload: MealRecommendRequest) -> dict:
    target_date = payload.target_date
    logs, context = _daily_payload(target_date)
    daily = context["summary"]
    meal_type = payload.meal_type or nutrition.infer_next_meal(logs)
    try:
        recommendation, ai_mode = await deepseek.recommend_meal(
            context["profile"],
            daily,
            meal_type,
            logs,
        )
    except deepseek.AIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "date": target_date.isoformat(),
        "meal_type": meal_type,
        "meal_label": nutrition.MEAL_LABELS.get(meal_type, "用餐"),
        "ai_mode": ai_mode,
        "daily": {
            "totals": daily["totals"],
            "target": daily["target"],
            "remaining": daily["remaining"],
            "status": daily["status"],
            "status_label": daily["status_label"],
            "exercise": daily["exercise"],
            "energy_balance": daily["energy_balance"],
        },
        "recommendation": recommendation,
    }


@router.post("/analyze")
async def analyze_meal(
    description: str = Form(""),
    meal_type: str = Form("lunch"),
    log_date: date | None = Form(None),
    photo: UploadFile | None = File(None),
) -> dict:
    description = description.strip()
    if len(description) > 500:
        raise HTTPException(status_code=422, detail="文字描述请控制在 500 字以内")

    meal_type = meal_type if meal_type in MEAL_TYPES else "lunch"
    entry_date = (log_date or date.today()).isoformat()

    photo_path = None
    image = None
    content_type = ""
    if photo is not None and photo.filename:
        content = await photo.read()
        content_type = (photo.content_type or "").lower()
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"图片不能超过 {settings.max_upload_bytes // (1024 * 1024)}MB",
            )
        if not content:
            raise HTTPException(status_code=400, detail="图片内容为空")
        if content_type in deepseek.VISION_MIME_TYPES:
            image = (content, content_type)
        elif len(description) < 2:
            raise HTTPException(
                status_code=422,
                detail="该图片格式暂不支持 AI 识别，请补充文字描述或改用 JPEG/PNG/WebP/GIF",
            )
        photo_path = _save_photo(photo, content)

    if len(description) < 2 and image is None:
        raise HTTPException(status_code=422, detail="请上传照片或描述这一餐吃了什么")

    profile = load_profile()
    metrics = compute_metrics(profile)
    ai_profile = {**profile, **metrics}

    try:
        analysis, ai_mode = await deepseek.analyze_diet(
            description, meal_type, ai_profile, image
        )
    except deepseek.AIError as exc:
        _delete_photo(photo_path)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    totals = analysis["totals"]
    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO diet_logs (log_date, meal_type, description, photo_path, "
            "calories, protein, fat, carbs, fiber, sugar, sodium, score, "
            "advice, tips, foods, confidence, ai_mode, vision_used) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry_date,
                meal_type,
                description,
                photo_path,
                totals["calories"],
                totals["protein"],
                totals["fat"],
                totals["carbs"],
                totals["fiber"],
                totals["sugar"],
                totals["sodium"],
                analysis["score"],
                json.dumps(analysis["advice"], ensure_ascii=False),
                json.dumps(analysis["tips"], ensure_ascii=False),
                json.dumps(analysis["foods"], ensure_ascii=False),
                analysis["confidence"],
                ai_mode,
                1 if (image is not None and ai_mode == "deepseek") else 0,
            ),
        )
        row = db.execute(
            "SELECT * FROM diet_logs WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()

    note = analysis["note"]
    if photo_path and image is None:
        note = (
            f"{note} 图片格式 {content_type or '未知'} 暂不支持 AI 识别"
            "（支持 JPEG/PNG/WebP/GIF），已保存留档。"
        )
    return {
        **_serialize(row),
        "note": note,
    }


@router.get("/logs")
def list_logs(
    limit: int = Query(default=20, ge=1, le=100),
    log_date: date | None = Query(default=None),
) -> dict:
    with get_db() as db:
        if log_date:
            rows = db.execute(
                "SELECT * FROM diet_logs WHERE log_date = ? "
                "ORDER BY id DESC LIMIT ?",
                (log_date.isoformat(), limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM diet_logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
    return {"items": [_serialize(row) for row in rows]}


@router.delete("/logs/{log_id}", status_code=204)
def delete_log(log_id: int) -> None:
    with get_db() as db:
        row = db.execute("SELECT * FROM diet_logs WHERE id = ?", (log_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="记录不存在")
        db.execute("DELETE FROM diet_logs WHERE id = ?", (log_id,))
    _delete_photo(row["photo_path"])
