from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query

from ..body_trends import analyze_body_records
from ..db import get_db
from ..health_metrics import compute_metrics
from ..schemas import BodyRecordCreate
from .profile import load_profile

router = APIRouter(prefix="/api/body", tags=["body"])

BODY_FIELDS = (
    "weight_kg",
    "body_fat_pct",
    "muscle_kg",
    "waist_cm",
    "sleep_hours",
    "resting_hr",
    "steps",
)


def serialize(row) -> dict:
    return dict(row)


def upsert_body_record(db, record: dict) -> None:
    db.execute(
        "INSERT INTO body_records "
        "(record_date, weight_kg, body_fat_pct, muscle_kg, waist_cm, sleep_hours, "
        "resting_hr, steps, notes, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(record_date) DO UPDATE SET "
        "weight_kg = COALESCE(excluded.weight_kg, body_records.weight_kg), "
        "body_fat_pct = COALESCE(excluded.body_fat_pct, body_records.body_fat_pct), "
        "muscle_kg = COALESCE(excluded.muscle_kg, body_records.muscle_kg), "
        "waist_cm = COALESCE(excluded.waist_cm, body_records.waist_cm), "
        "sleep_hours = COALESCE(excluded.sleep_hours, body_records.sleep_hours), "
        "resting_hr = COALESCE(excluded.resting_hr, body_records.resting_hr), "
        "steps = COALESCE(excluded.steps, body_records.steps), "
        "notes = CASE WHEN excluded.notes != '' THEN excluded.notes "
        "ELSE body_records.notes END, "
        "source = excluded.source, "
        "updated_at = datetime('now', 'localtime')",
        (
            record["record_date"],
            record.get("weight_kg"),
            record.get("body_fat_pct"),
            record.get("muscle_kg"),
            record.get("waist_cm"),
            record.get("sleep_hours"),
            record.get("resting_hr"),
            record.get("steps"),
            record.get("notes", ""),
            record.get("source", "manual"),
        ),
    )


def sync_profile_weight(db) -> None:
    row = db.execute(
        "SELECT weight_kg FROM body_records WHERE weight_kg IS NOT NULL "
        "ORDER BY record_date DESC LIMIT 1"
    ).fetchone()
    if row is not None:
        db.execute(
            "UPDATE profile SET weight_kg = ?, "
            "updated_at = datetime('now', 'localtime') WHERE id = 1",
            (row["weight_kg"],),
        )


@router.get("/records")
def list_records(
    limit: int = Query(default=120, ge=1, le=500),
    days: int | None = Query(default=None, ge=1, le=3650),
) -> dict:
    with get_db() as db:
        if days:
            cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
            rows = db.execute(
                "SELECT * FROM body_records WHERE record_date >= ? "
                "ORDER BY record_date DESC LIMIT ?",
                (cutoff, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM body_records ORDER BY record_date DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return {"items": [serialize(row) for row in rows]}


@router.post("/records", status_code=201)
def create_record(payload: BodyRecordCreate) -> dict:
    values = payload.dict()
    record = {
        "record_date": values["record_date"].isoformat(),
        **{field: values.get(field) for field in BODY_FIELDS},
        "notes": values.get("notes") or "",
        "source": values.get("source") or "manual",
    }
    with get_db() as db:
        upsert_body_record(db, record)
        sync_profile_weight(db)
        row = db.execute(
            "SELECT * FROM body_records WHERE record_date = ?",
            (record["record_date"],),
        ).fetchone()
    return serialize(row)


@router.delete("/records/{record_id}", status_code=204)
def delete_record(record_id: int) -> None:
    with get_db() as db:
        row = db.execute(
            "SELECT id FROM body_records WHERE id = ?", (record_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="记录不存在")
        db.execute("DELETE FROM body_records WHERE id = ?", (record_id,))
        sync_profile_weight(db)


@router.get("/summary")
def summary(days: int = Query(default=90, ge=7, le=3650)) -> dict:
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM body_records WHERE record_date >= ? "
            "ORDER BY record_date ASC",
            (cutoff,),
        ).fetchall()
    records = [dict(row) for row in rows]
    profile = load_profile()
    metrics = compute_metrics(profile)
    return analyze_body_records(records, profile, metrics)
