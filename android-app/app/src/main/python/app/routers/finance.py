from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from ..db import get_db
from ..schemas import FinanceCreate

router = APIRouter(prefix="/api/finance", tags=["finance"])

MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _check_month(month: str) -> str:
    if not MONTH_PATTERN.match(month):
        raise HTTPException(status_code=422, detail="月份格式应为 YYYY-MM")
    return month


def _serialize(row) -> dict:
    return dict(row)


@router.get("/records")
def list_records(
    month: str | None = Query(default=None),
    record_type: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    conditions = []
    params: list = []
    if month:
        conditions.append("record_date LIKE ?")
        params.append(f"{_check_month(month)}-%")
    if record_type in {"expense", "income"}:
        conditions.append("type = ?")
        params.append(record_type)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    with get_db() as db:
        rows = db.execute(
            f"SELECT * FROM finance_records {where} "  # noqa: S608
            "ORDER BY record_date DESC, id DESC LIMIT ?",
            params,
        ).fetchall()
    return {"items": [_serialize(row) for row in rows]}


@router.post("/records", status_code=201)
def create_record(payload: FinanceCreate) -> dict:
    values = (
        payload.record_date.isoformat(),
        payload.type,
        payload.amount,
        payload.category,
        payload.note,
        payload.source,
        payload.external_id,
    )
    with get_db() as db:
        if payload.external_id:
            existing = db.execute(
                "SELECT * FROM finance_records WHERE external_id = ?",
                (payload.external_id,),
            ).fetchone()
            if existing:
                db.execute(
                    "UPDATE finance_records SET record_date = ?, type = ?, "
                    "amount = ?, category = ?, note = ?, source = ? WHERE id = ?",
                    (
                        payload.record_date.isoformat(),
                        payload.type,
                        payload.amount,
                        payload.category,
                        payload.note,
                        payload.source,
                        existing["id"],
                    ),
                )
                row = db.execute(
                    "SELECT * FROM finance_records WHERE id = ?", (existing["id"],)
                ).fetchone()
                return {**_serialize(row), "updated": True}

        cursor = db.execute(
            "INSERT INTO finance_records (record_date, type, amount, category, "
            "note, source, external_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            values,
        )
        row = db.execute(
            "SELECT * FROM finance_records WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return {**_serialize(row), "updated": False}


@router.delete("/records/{record_id}", status_code=204)
def delete_record(record_id: int) -> None:
    with get_db() as db:
        row = db.execute(
            "SELECT id FROM finance_records WHERE id = ?", (record_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="记录不存在")
        db.execute("DELETE FROM finance_records WHERE id = ?", (record_id,))


@router.get("/summary")
def summary(month: str | None = Query(default=None)) -> dict:
    target = month or date.today().strftime("%Y-%m")
    _check_month(target)

    with get_db() as db:
        rows = db.execute(
            "SELECT type, category, SUM(amount) AS total, COUNT(*) AS count "
            "FROM finance_records WHERE record_date LIKE ? "
            "GROUP BY type, category ORDER BY total DESC",
            (f"{target}-%",),
        ).fetchall()

    income = 0.0
    expense = 0.0
    by_category: list[dict] = []
    for row in rows:
        total = round(float(row["total"] or 0), 2)
        if row["type"] == "income":
            income += total
        else:
            expense += total
        by_category.append(
            {
                "type": row["type"],
                "category": row["category"],
                "amount": total,
                "count": row["count"],
            }
        )

    expense_categories = [item for item in by_category if item["type"] == "expense"]
    if expense > 0:
        for item in expense_categories:
            item["ratio"] = round(item["amount"] / expense, 4)

    with get_db() as db:
        count_row = db.execute(
            "SELECT COUNT(*) AS count FROM finance_records WHERE record_date LIKE ?",
            (f"{target}-%",),
        ).fetchone()

    return {
        "month": target,
        "income": round(income, 2),
        "expense": round(expense, 2),
        "balance": round(income - expense, 2),
        "count": count_row["count"] if count_row else 0,
        "by_category": by_category,
    }
