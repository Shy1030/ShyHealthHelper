from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from .. import deepseek
from ..config import settings
from ..db import get_db
from ..health_metrics import compute_metrics
from ..predictions import PHASE_INFO, analyze_cycles
from ..schemas import (
    ExerciseDescribeRequest,
    ExerciseLogCreate,
    ExercisePlanRequest,
)
from ..uploads import delete_image, save_image
from .cycle import _load_periods
from .profile import load_profile

router = APIRouter(prefix="/api/exercise", tags=["exercise"])

SOURCE_LABELS = {
    "screenshot": "截图识别",
    "description": "文字描述",
    "xiaomi": "小米手环",
    "manual": "手动",
}


def _serialize(row) -> dict:
    data = dict(row)
    try:
        data["plan"] = json.loads(data.get("plan") or "{}")
    except (TypeError, json.JSONDecodeError):
        data["plan"] = {}
    return data


def _serialize_log(row) -> dict:
    data = dict(row)
    try:
        data["raw"] = json.loads(data.get("raw") or "{}")
    except (TypeError, json.JSONDecodeError):
        data["raw"] = {}
    data["photo_url"] = (
        f"/uploads/{data['photo_path']}" if data.get("photo_path") else None
    )
    data["source_label"] = SOURCE_LABELS.get(data.get("source"), data.get("source"))
    data["calories_estimated"] = bool(data.get("calories_estimated"))
    data["duration_estimated"] = bool(data.get("duration_estimated"))
    return data


def _insert_log(
    db,
    log: dict,
    *,
    source: str,
    ai_mode: str,
    photo_path: str | None = None,
    raw: dict | None = None,
):
    cursor = db.execute(
        "INSERT INTO exercise_logs "
        "(log_date, start_time, activity, duration_min, calories, distance_km, "
        "steps, avg_heart_rate, notes, source, photo_path, ai_mode, "
        "calories_estimated, duration_estimated, calorie_basis, raw) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            log.get("log_date") or date.today().isoformat(),
            log.get("start_time"),
            (log.get("activity") or "运动")[:40],
            log.get("duration_min"),
            log.get("calories"),
            log.get("distance_km"),
            log.get("steps"),
            log.get("avg_heart_rate"),
            (log.get("notes") or "")[:300],
            source,
            photo_path,
            ai_mode,
            1 if log.get("calories_estimated") else 0,
            1 if log.get("duration_estimated") else 0,
            str(log.get("calorie_basis") or "")[:300],
            json.dumps(raw or log, ensure_ascii=False),
        ),
    )
    return db.execute(
        "SELECT * FROM exercise_logs WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()


def _activity_snapshot(days: int = 14) -> dict:
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM exercise_logs WHERE log_date >= ? ORDER BY log_date DESC",
            (cutoff,),
        ).fetchall()
    records = [dict(row) for row in rows]
    by_activity: dict[str, float] = defaultdict(float)
    total_duration = 0.0
    total_calories = 0.0
    estimated_calories = 0.0
    estimated_sessions = 0
    for record in records:
        duration = float(record.get("duration_min") or 0)
        calories = float(record.get("calories") or 0)
        total_duration += duration
        total_calories += calories
        if record.get("calories_estimated"):
            estimated_calories += calories
            estimated_sessions += 1
        by_activity[record.get("activity") or "运动"] += duration
    top = sorted(by_activity.items(), key=lambda item: item[1], reverse=True)[:3]
    return {
        "days": days,
        "sessions": len(records),
        "active_days": len({record["log_date"] for record in records}),
        "total_duration_min": round(total_duration, 1),
        "total_calories": round(total_calories, 1),
        "estimated_calories": round(estimated_calories, 1),
        "estimated_sessions": estimated_sessions,
        "by_activity": [{"activity": name, "duration_min": round(value, 1)} for name, value in top],
    }


@router.post("/plan", status_code=201)
async def generate_plan(payload: ExercisePlanRequest | None = None) -> dict:
    preferences = (payload.preferences if payload else "").strip()
    profile = load_profile()
    missing = [
        label
        for label, key in (
            ("出生年份", "birth_year"),
            ("身高", "height_cm"),
            ("体重", "weight_kg"),
        )
        if not profile.get(key)
    ]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"请先在身体档案中填写：{'、'.join(missing)}",
        )

    analysis = analyze_cycles(_load_periods())
    current = analysis["current"]
    phase = current["phase"]
    metrics = compute_metrics(profile)
    activity = _activity_snapshot()

    try:
        plan, ai_mode = await deepseek.build_exercise_plan(
            profile, metrics, phase, current["cycle_day"], activity, preferences
        )
    except deepseek.AIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if preferences:
        plan["preferences"] = preferences

    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO exercise_plans (cycle_phase, plan, ai_mode) VALUES (?, ?, ?)",
            (phase, json.dumps(plan, ensure_ascii=False), ai_mode),
        )
        row = db.execute(
            "SELECT * FROM exercise_plans WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()

    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "ai_mode": row["ai_mode"],
        "cycle_phase": phase,
        "phase_label": PHASE_INFO.get(phase, PHASE_INFO["unknown"])["label"],
        "cycle_day": current["cycle_day"],
        "metrics": metrics,
        "activity": activity,
        "preferences": preferences,
        "plan": plan,
    }


@router.get("/plans")
def list_plans(limit: int = Query(default=5, ge=1, le=20)) -> dict:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM exercise_plans ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    items = []
    for row in rows:
        item = _serialize(row)
        item["phase_label"] = PHASE_INFO.get(
            item["cycle_phase"], PHASE_INFO["unknown"]
        )["label"]
        items.append(item)
    return {"items": items}


@router.post("/logs/analyze", status_code=201)
async def analyze_screenshot(
    photo: UploadFile = File(...),
    note: str = Form(""),
) -> dict:
    content = await photo.read()
    content_type = (photo.content_type or "").lower()
    if content_type not in deepseek.VISION_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail="请上传 JPG/PNG/WebP/GIF 格式的运动截图",
        )
    if not content:
        raise HTTPException(status_code=400, detail="截图内容为空")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"图片不能超过 {settings.max_upload_bytes // (1024 * 1024)}MB",
        )

    photo_path = save_image(content, content_type)
    profile = load_profile()
    metrics = compute_metrics(profile)
    try:
        analysis, ai_mode = await deepseek.analyze_exercise_screenshot(
            note.strip(), (content, content_type), {**profile, **metrics}
        )
    except deepseek.AIError as exc:
        delete_image(photo_path)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    records = analysis["records"]
    if not records:
        delete_image(photo_path)
        raise HTTPException(
            status_code=422,
            detail="没有从截图中识别到运动记录，请换一张更清晰的截图或补充说明",
        )

    saved = []
    with get_db() as db:
        for index, record in enumerate(records):
            row = _insert_log(
                db,
                record,
                source="screenshot",
                ai_mode=ai_mode,
                photo_path=photo_path if index == 0 else None,
                raw=analysis,
            )
            saved.append(_serialize_log(row))

    return {
        "records": saved,
        "summary": analysis["summary"],
        "confidence": analysis["confidence"],
        "note": analysis["note"],
        "ai_mode": ai_mode,
        "photo_url": f"/uploads/{photo_path}",
        "estimated_sessions": analysis.get("estimated_sessions", 0),
        "estimated_calories": analysis.get("estimated_calories", 0),
    }


@router.post("/logs/describe", status_code=201)
async def describe_exercise(payload: ExerciseDescribeRequest) -> dict:
    description = payload.description.strip()
    if len(description) < 2:
        raise HTTPException(status_code=422, detail="请描述一下今天的运动情况")

    profile = load_profile()
    metrics = compute_metrics(profile)
    try:
        analysis, ai_mode = await deepseek.analyze_exercise_description(
            description, payload.log_date, {**profile, **metrics}
        )
    except deepseek.AIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    records = analysis["records"]
    if not records:
        raise HTTPException(
            status_code=422,
            detail="没有从描述中识别到运动，请补充运动类型或时长",
        )

    saved = []
    with get_db() as db:
        for record in records:
            record["notes"] = record.get("notes") or description[:300]
            row = _insert_log(
                db,
                record,
                source="description",
                ai_mode=ai_mode,
                raw=analysis,
            )
            saved.append(_serialize_log(row))

    return {
        "records": saved,
        "summary": analysis["summary"],
        "confidence": analysis["confidence"],
        "note": analysis["note"],
        "ai_mode": ai_mode,
        "description": description,
        "estimated_sessions": analysis.get("estimated_sessions", 0),
        "estimated_calories": analysis.get("estimated_calories", 0),
    }


@router.get("/logs")
def list_logs(
    limit: int = Query(default=30, ge=1, le=200),
    days: int | None = Query(default=None, ge=1, le=3650),
) -> dict:
    with get_db() as db:
        if days:
            cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
            rows = db.execute(
                "SELECT * FROM exercise_logs WHERE log_date >= ? "
                "ORDER BY log_date DESC, id DESC LIMIT ?",
                (cutoff, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM exercise_logs ORDER BY log_date DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return {"items": [_serialize_log(row) for row in rows]}


@router.post("/logs", status_code=201)
def create_log(payload: ExerciseLogCreate) -> dict:
    data = payload.dict()
    data["log_date"] = data["log_date"].isoformat()
    with get_db() as db:
        row = _insert_log(
            db,
            data,
            source=data.get("source") or "manual",
            ai_mode="manual",
            raw=data,
        )
    return _serialize_log(row)


@router.delete("/logs/{log_id}", status_code=204)
def delete_log(log_id: int) -> None:
    photo_path = None
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM exercise_logs WHERE id = ?", (log_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="运动记录不存在")
        photo_path = row["photo_path"]
        db.execute("DELETE FROM exercise_logs WHERE id = ?", (log_id,))
        if photo_path:
            remaining = db.execute(
                "SELECT COUNT(*) AS count FROM exercise_logs WHERE photo_path = ?",
                (photo_path,),
            ).fetchone()
            if remaining["count"] > 0:
                photo_path = None
    delete_image(photo_path)


@router.get("/summary")
def activity_summary(days: int = Query(default=30, ge=7, le=3650)) -> dict:
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM exercise_logs WHERE log_date >= ? ORDER BY log_date ASC",
            (cutoff,),
        ).fetchall()
    records = [dict(row) for row in rows]

    total_duration = sum(float(record.get("duration_min") or 0) for record in records)
    total_calories = sum(float(record.get("calories") or 0) for record in records)
    estimated_records = [
        record for record in records if record.get("calories_estimated")
    ]
    estimated_calories = sum(
        float(record.get("calories") or 0) for record in estimated_records
    )
    total_distance = sum(float(record.get("distance_km") or 0) for record in records)
    total_steps = sum(int(record.get("steps") or 0) for record in records)
    active_days = len({record["log_date"] for record in records})

    by_activity: dict[str, dict] = {}
    for record in records:
        name = record.get("activity") or "运动"
        bucket = by_activity.setdefault(name, {"activity": name, "count": 0, "duration_min": 0.0})
        bucket["count"] += 1
        bucket["duration_min"] += float(record.get("duration_min") or 0)
    activities = sorted(
        by_activity.values(), key=lambda item: item["duration_min"], reverse=True
    )[:5]
    for item in activities:
        item["duration_min"] = round(item["duration_min"], 1)

    today = date.today()
    recent_cutoff = (today - timedelta(days=6)).isoformat()
    previous_start = (today - timedelta(days=13)).isoformat()
    recent = [r for r in records if r["log_date"] >= recent_cutoff]
    previous = [
        r for r in records if previous_start <= r["log_date"] < recent_cutoff
    ]
    recent_minutes = sum(float(r.get("duration_min") or 0) for r in recent)
    previous_minutes = sum(float(r.get("duration_min") or 0) for r in previous)
    weekly_change = round(recent_minutes - previous_minutes, 1)

    suggestions: list[str] = []
    if not records:
        suggestions.append("还没有运动记录，可以上传手环截图或导入导出文件开始。")
    else:
        weekly_minutes = total_duration / max(1, days / 7)
        if weekly_minutes < 150:
            suggestions.append(
                f"平均每周运动约 {int(weekly_minutes)} 分钟，低于 150 分钟的建议量。"
                "可以从每周 3 次快走或骑行开始。"
            )
        else:
            suggestions.append("每周运动时长已达到基础建议量，注意安排 1-2 天恢复。")
        if active_days < days / 7 * 2:
            suggestions.append("运动天数偏少，建议把训练分散到一周中的 3-5 天。")
        if weekly_change >= 30:
            suggestions.append("本周运动量比上周明显增加，注意循序渐进并保证睡眠。")
        if total_calories:
            suggestions.append(f"近 {days} 天累计消耗约 {int(total_calories)} 千卡。")
        suggestions.append("运动记录来自截图或手环导入时可能不完整，可结合身体感受调整。")

    return {
        "days": days,
        "from_date": cutoff,
        "to_date": today.isoformat(),
        "sessions": len(records),
        "active_days": active_days,
        "total_duration_min": round(total_duration, 1),
        "total_calories": round(total_calories, 1),
        "estimated_calories": round(estimated_calories, 1),
        "estimated_sessions": len(estimated_records),
        "total_distance_km": round(total_distance, 2),
        "total_steps": total_steps,
        "weekly_change_min": weekly_change,
        "by_activity": activities,
        "suggestions": suggestions,
    }
