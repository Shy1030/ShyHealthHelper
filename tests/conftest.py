import os
import tempfile
from pathlib import Path

import pytest

_DATA_DIR = Path(tempfile.mkdtemp(prefix="mooncare-test-"))
os.environ["APP_DATA_DIR"] = str(_DATA_DIR)
os.environ["AI_MOCK"] = "1"
os.environ["DEEPSEEK_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app import ai_store  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    ai_store.clear_ai_settings()
    with get_db() as db:
        for table in (
            "periods",
            "diet_logs",
            "exercise_plans",
            "exercise_logs",
            "body_records",
            "finance_records",
            "chat_messages",
        ):
            db.execute(f"DELETE FROM {table}")  # noqa: S608
        db.execute(
            "UPDATE profile SET nickname = '我的身体档案', sex = 'female', "
            "birth_year = NULL, height_cm = NULL, weight_kg = NULL, "
            "activity_level = 'light', goal = 'maintain', "
            "target_weight_kg = NULL, target_date = NULL, injuries = '' "
            "WHERE id = 1"
        )
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        yield test_client
