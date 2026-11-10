from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from ..db import get_db
from ..predictions import analyze_cycles, build_calendar, parse_date
from ..schemas import PeriodCreate, PeriodUpdate

router = APIRouter(prefix="/api/cycle", tags=["cycle"])


def _load_periods() -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT id, start_date, end_date, flow, symptoms, notes "
            "FROM periods ORDER BY start_date ASC"
        ).fetchall()
    return [dict(row) for row in rows]


def _serialize(row) -> dict:
    return dict(row)


@router.get("/overview")
def overview(today: date | None = Query(default=None)) -> dict:
    return analyze_cycles(_load_periods(), today)


@router.get("/periods")
def list_periods() -> dict:
    periods = _load_periods()
    periods.reverse()
    return {"items": periods, "count": len(periods)}


@router.post("/periods", status_code=201)
def create_period(payload: PeriodCreate) -> dict:
    with get_db() as db:
        existing = db.execute(
            "SELECT id FROM periods WHERE start_date = ?",
            (payload.start_date.isoformat(),),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="该开始日期已有记录")

        cursor = db.execute(
            "INSERT INTO periods (start_date, end_date, flow, symptoms, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                payload.start_date.isoformat(),
                payload.end_date.isoformat() if payload.end_date else None,
                payload.flow,
                payload.symptoms,
                payload.notes,
            ),
        )
        row = db.execute(
            "SELECT * FROM periods WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return _serialize(row)


@router.put("/periods/{period_id}")
def update_period(period_id: int, payload: PeriodUpdate) -> dict:
    with get_db() as db:
        row = db.execute("SELECT * FROM periods WHERE id = ?", (period_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="记录不存在")
        current = dict(row)
        values = payload.dict(exclude_unset=True)

        start = values.get("start_date")
        start = parse_date(start) if start else parse_date(current["start_date"])
        end_value = values.get("end_date", current["end_date"])
        end = parse_date(end_value) if end_value else None

        if end is not None:
            if end < start:
                raise HTTPException(status_code=422, detail="结束日期不能早于开始日期")
            if (end - start).days + 1 > 15:
                raise HTTPException(status_code=422, detail="单次经期不能超过 15 天")

        updates = {
            "start_date": start.isoformat(),
            "end_date": end.isoformat() if end else None,
            "flow": values.get("flow", current["flow"]),
            "symptoms": values.get("symptoms", current["symptoms"]),
            "notes": values.get("notes", current["notes"]),
        }

        conflict = db.execute(
            "SELECT id FROM periods WHERE start_date = ? AND id != ?",
            (updates["start_date"], period_id),
        ).fetchone()
        if conflict:
            raise HTTPException(status_code=409, detail="该开始日期已有记录")

        db.execute(
            "UPDATE periods SET start_date = ?, end_date = ?, flow = ?, "
            "symptoms = ?, notes = ? WHERE id = ?",
            (
                updates["start_date"],
                updates["end_date"],
                updates["flow"],
                updates["symptoms"],
                updates["notes"],
                period_id,
            ),
        )
        row = db.execute("SELECT * FROM periods WHERE id = ?", (period_id,)).fetchone()
    return _serialize(row)


@router.delete("/periods/{period_id}", status_code=204)
def delete_period(period_id: int) -> None:
    with get_db() as db:
        row = db.execute("SELECT id FROM periods WHERE id = ?", (period_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="记录不存在")
        db.execute("DELETE FROM periods WHERE id = ?", (period_id,))


@router.get("/calendar")
def calendar(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    today: date | None = Query(default=None),
) -> dict:
    periods = _load_periods()
    analysis = analyze_cycles(periods, today)
    return build_calendar(year, month, periods, analysis, today)
