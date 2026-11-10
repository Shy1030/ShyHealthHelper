from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    nickname TEXT NOT NULL DEFAULT '我的身体档案',
    sex TEXT NOT NULL DEFAULT 'female',
    birth_year INTEGER,
    height_cm REAL,
    weight_kg REAL,
    activity_level TEXT NOT NULL DEFAULT 'light',
    goal TEXT NOT NULL DEFAULT 'maintain',
    target_weight_kg REAL,
    target_date TEXT,
    injuries TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_date TEXT NOT NULL UNIQUE,
    end_date TEXT,
    flow TEXT NOT NULL DEFAULT 'medium',
    symptoms TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS diet_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date TEXT NOT NULL,
    meal_type TEXT NOT NULL,
    description TEXT NOT NULL,
    photo_path TEXT,
    calories REAL NOT NULL DEFAULT 0,
    protein REAL NOT NULL DEFAULT 0,
    fat REAL NOT NULL DEFAULT 0,
    carbs REAL NOT NULL DEFAULT 0,
    fiber REAL NOT NULL DEFAULT 0,
    sugar REAL NOT NULL DEFAULT 0,
    sodium REAL NOT NULL DEFAULT 0,
    score INTEGER,
    advice TEXT NOT NULL DEFAULT '[]',
    tips TEXT NOT NULL DEFAULT '[]',
    foods TEXT NOT NULL DEFAULT '[]',
    confidence TEXT NOT NULL DEFAULT 'medium',
    ai_mode TEXT NOT NULL DEFAULT 'mock',
    vision_used INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS exercise_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_phase TEXT NOT NULL DEFAULT 'unknown',
    plan TEXT NOT NULL,
    ai_mode TEXT NOT NULL DEFAULT 'mock',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS exercise_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date TEXT NOT NULL,
    start_time TEXT,
    activity TEXT NOT NULL DEFAULT '运动',
    duration_min REAL,
    calories REAL,
    distance_km REAL,
    steps INTEGER,
    avg_heart_rate INTEGER,
    notes TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manual',
    photo_path TEXT,
    ai_mode TEXT NOT NULL DEFAULT 'manual',
    calories_estimated INTEGER NOT NULL DEFAULT 0,
    duration_estimated INTEGER NOT NULL DEFAULT 0,
    calorie_basis TEXT NOT NULL DEFAULT '',
    raw TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS body_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_date TEXT NOT NULL UNIQUE,
    weight_kg REAL,
    body_fat_pct REAL,
    muscle_kg REAL,
    waist_cm REAL,
    sleep_hours REAL,
    resting_hr INTEGER,
    steps INTEGER,
    notes TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS finance_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_date TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('expense', 'income')),
    amount REAL NOT NULL CHECK (amount > 0),
    category TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'web',
    external_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_periods_start ON periods(start_date);
CREATE INDEX IF NOT EXISTS idx_diet_date ON diet_logs(log_date);
CREATE INDEX IF NOT EXISTS idx_exercise_date ON exercise_logs(log_date);
CREATE INDEX IF NOT EXISTS idx_body_date ON body_records(record_date);
CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_finance_date ON finance_records(record_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_finance_external
    ON finance_records(external_id) WHERE external_id IS NOT NULL;
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    settings.ensure_dirs()
    with get_db() as db:
        db.executescript(SCHEMA)
        columns = {
            row["name"] for row in db.execute("PRAGMA table_info(diet_logs)").fetchall()
        }
        if "vision_used" not in columns:
            db.execute(
                "ALTER TABLE diet_logs ADD COLUMN vision_used INTEGER NOT NULL DEFAULT 0"
            )
        profile_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(profile)").fetchall()
        }
        if "target_weight_kg" not in profile_columns:
            db.execute("ALTER TABLE profile ADD COLUMN target_weight_kg REAL")
        if "target_date" not in profile_columns:
            db.execute("ALTER TABLE profile ADD COLUMN target_date TEXT")
        exercise_columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(exercise_logs)").fetchall()
        }
        if "calories_estimated" not in exercise_columns:
            db.execute(
                "ALTER TABLE exercise_logs ADD COLUMN calories_estimated "
                "INTEGER NOT NULL DEFAULT 0"
            )
        if "duration_estimated" not in exercise_columns:
            db.execute(
                "ALTER TABLE exercise_logs ADD COLUMN duration_estimated "
                "INTEGER NOT NULL DEFAULT 0"
            )
        if "calorie_basis" not in exercise_columns:
            db.execute(
                "ALTER TABLE exercise_logs ADD COLUMN calorie_basis "
                "TEXT NOT NULL DEFAULT ''"
            )
        db.execute("INSERT OR IGNORE INTO profile (id) VALUES (1)")


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None
