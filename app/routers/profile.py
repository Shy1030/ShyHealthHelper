from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException

from ..db import get_db, row_to_dict
from ..health_metrics import compute_metrics
from ..schemas import ProfileUpdate

router = APIRouter(prefix="/api/profile", tags=["profile"])


def load_profile() -> dict:
    with get_db() as db:
        row = db.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    profile = row_to_dict(row)
    if profile is None:
        raise HTTPException(status_code=500, detail="身体档案初始化失败")
    return profile


@router.get("")
def get_profile() -> dict:
    profile = load_profile()
    return {"profile": profile, "metrics": compute_metrics(profile)}


@router.put("")
def update_profile(payload: ProfileUpdate) -> dict:
    values = payload.dict(exclude_unset=True)
    if not values:
        return get_profile()
    if values.get("target_date") is not None:
        values["target_date"] = values["target_date"].isoformat()

    columns = []
    params: list = []
    for key, value in values.items():
        columns.append(f"{key} = ?")
        params.append(value)
    columns.append("updated_at = datetime('now', 'localtime')")

    with get_db() as db:
        db.execute(
            f"UPDATE profile SET {', '.join(columns)} WHERE id = 1",  # noqa: S608
            params,
        )
        if values.get("weight_kg") is not None:
            db.execute(
                "INSERT INTO body_records (record_date, weight_kg, source) "
                "VALUES (?, ?, 'manual') "
                "ON CONFLICT(record_date) DO UPDATE SET "
                "weight_kg = excluded.weight_kg, "
                "source = 'manual', "
                "updated_at = datetime('now', 'localtime')",
                (date.today().isoformat(), values["weight_kg"]),
            )
        row = db.execute("SELECT * FROM profile WHERE id = 1").fetchone()

    profile = row_to_dict(row)
    return {"profile": profile, "metrics": compute_metrics(profile)}
