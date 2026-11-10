from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Query

from ..db import get_db
from .diet import _daily_payload

router = APIRouter(prefix="/api/home", tags=["home"])


@router.get("/today")
def today_overview(date_: date | None = Query(default=None, alias="date")) -> dict:
    target_date = date_ or date.today()
    _, context = _daily_payload(target_date)
    daily = context["summary"]

    with get_db() as db:
        rows = db.execute(
            "SELECT type, COALESCE(SUM(amount), 0) AS amount, COUNT(*) AS count "
            "FROM finance_records WHERE record_date = ? GROUP BY type",
            (target_date.isoformat(),),
        ).fetchall()

    expense = 0.0
    income = 0.0
    count = 0
    for row in rows:
        count += int(row["count"] or 0)
        if row["type"] == "income":
            income += float(row["amount"] or 0)
        else:
            expense += float(row["amount"] or 0)

    with get_db() as db:
        plan_row = db.execute(
            "SELECT * FROM exercise_plans ORDER BY id DESC LIMIT 1"
        ).fetchone()

    exercise_plan = None
    if plan_row is not None:
        try:
            plan_data = json.loads(plan_row["plan"] or "{}")
        except (TypeError, json.JSONDecodeError):
            plan_data = {}
        weekly = plan_data.get("weekly_plan")
        if not isinstance(weekly, list):
            weekly = []
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
            target_date.weekday()
        ]
        today_item = next(
            (item for item in weekly if item.get("day") == weekday), None
        )
        if today_item is None and 0 <= target_date.weekday() < len(weekly):
            today_item = weekly[target_date.weekday()]
        exercise_plan = {
            "id": plan_row["id"],
            "created_at": plan_row["created_at"],
            "cycle_phase": plan_row["cycle_phase"],
            "weekday": weekday,
            "summary": plan_data.get("summary") or "",
            "phase_note": plan_data.get("phase_note") or "",
            "preferences": plan_data.get("preferences") or "",
            "today": today_item,
        }

    exercise = daily["exercise"]["today"]
    totals = daily["totals"]
    return {
        "date": target_date.isoformat(),
        "diet": {
            "calories": totals["calories"],
            "protein": totals["protein"],
            "fat": totals["fat"],
            "carbs": totals["carbs"],
            "fiber": totals["fiber"],
            "target_calories": daily["target"]["calories"],
            "remaining_calories": daily["remaining"]["calories"],
            "status": daily["status"],
            "status_label": daily["status_label"],
            "recorded_meals": daily["recorded_meals"],
            "energy_balance": daily["energy_balance"],
        },
        "exercise": {
            "sessions": exercise["sessions"],
            "active_days": exercise["active_days"],
            "duration_min": exercise["duration_min"],
            "calories": exercise["calories"],
            "estimated_calories": exercise.get("estimated_calories", 0),
            "estimated_sessions": exercise.get("estimated_sessions", 0),
        },
        "exercise_plan": exercise_plan,
        "finance": {
            "expense": round(expense, 2),
            "income": round(income, 2),
            "balance": round(income - expense, 2),
            "count": count,
        },
    }
