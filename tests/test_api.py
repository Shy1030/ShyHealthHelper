from __future__ import annotations

import pytest

from app.config import settings


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mock_mode"] is True
    assert body["ai_mode"] == "mock"


def test_root_serves_pwa(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "ShyHealthHelper" in response.text
    assert "manifest.webmanifest" in response.text


def test_profile_update_and_metrics(client):
    response = client.put(
        "/api/profile",
        json={
            "birth_year": 2000,
            "height_cm": 165,
            "weight_kg": 55,
            "activity_level": "moderate",
            "goal": "maintain",
            "injuries": "膝盖轻微不适",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["height_cm"] == 165
    assert body["profile"]["injuries"] == "膝盖轻微不适"
    assert body["metrics"]["bmi"] == 20.2
    assert body["metrics"]["bmr"] > 0
    assert body["metrics"]["tdee"] > body["metrics"]["bmr"]

    fetched = client.get("/api/profile").json()
    assert fetched["profile"]["weight_kg"] == 55


def test_period_crud_and_prediction(client):
    first = client.post(
        "/api/cycle/periods",
        json={
            "start_date": "2026-11-01",
            "end_date": "2026-11-05",
            "flow": "medium",
            "symptoms": "腰酸",
        },
    )
    assert first.status_code == 201
    period_id = first.json()["id"]

    duplicate = client.post(
        "/api/cycle/periods",
        json={"start_date": "2026-11-01", "flow": "light"},
    )
    assert duplicate.status_code == 409

    invalid = client.post(
        "/api/cycle/periods",
        json={"start_date": "2026-11-10", "end_date": "2026-11-01"},
    )
    assert invalid.status_code == 422

    overview = client.get("/api/cycle/overview?today=2026-11-20").json()
    assert overview["has_data"] is True
    assert overview["prediction"]["next_period_start"] == "2026-11-29"
    assert overview["current"]["cycle_day"] == 20
    assert overview["prediction"]["average_period_length"] == 5
    assert overview["history"][0]["symptoms"] == "腰酸"

    calendar = client.get(
        "/api/cycle/calendar?year=2026&month=11&today=2026-11-20"
    ).json()
    days = {item["date"]: item for item in calendar["days"]}
    assert days["2026-11-01"]["actual"] is True
    assert days["2026-11-29"]["predicted"] is True

    updated = client.put(
        f"/api/cycle/periods/{period_id}", json={"end_date": "2026-11-06"}
    )
    assert updated.status_code == 200
    assert updated.json()["end_date"] == "2026-11-06"

    deleted = client.delete(f"/api/cycle/periods/{period_id}")
    assert deleted.status_code == 204
    assert client.get("/api/cycle/overview").json()["has_data"] is False


def test_diet_analysis_photo_and_delete(client):
    client.put(
        "/api/profile",
        json={"height_cm": 165, "weight_kg": 55, "goal": "lose"},
    )
    response = client.post(
        "/api/diet/analyze",
        data={"description": "米饭、清蒸鱼、炒青菜", "meal_type": "lunch"},
        files={"photo": ("meal.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ai_mode"] == "mock"
    assert body["calories"] > 0
    assert body["meal_type"] == "lunch"
    assert body["photo_url"].startswith("/uploads/")
    assert body["vision_used"] is False
    assert "估算" in body["note"]
    assert isinstance(body["advice"], list) and body["advice"]

    photo_path = settings.upload_dir / body["photo_path"]
    assert photo_path.is_file()

    logs = client.get("/api/diet/logs").json()
    assert len(logs["items"]) == 1

    bad = client.post(
        "/api/diet/analyze",
        data={"description": "测试", "meal_type": "lunch"},
        files={"photo": ("note.txt", b"hello", "text/plain")},
    )
    assert bad.status_code == 400

    deleted = client.delete(f"/api/diet/logs/{body['id']}")
    assert deleted.status_code == 204
    assert not photo_path.exists()
    assert client.get("/api/diet/logs").json()["items"] == []


def test_diet_requires_photo_or_description(client):
    empty = client.post(
        "/api/diet/analyze",
        data={"description": "  ", "meal_type": "lunch"},
    )
    assert empty.status_code == 422

    photo_only = client.post(
        "/api/diet/analyze",
        data={"meal_type": "lunch"},
        files={"photo": ("meal.jpg", b"\xff\xd8\xff" + b"0" * 64, "image/jpeg")},
    )
    assert photo_only.status_code == 200
    body = photo_only.json()
    assert body["description"] == ""
    assert body["vision_used"] is False
    assert "估算" in body["note"]


def test_diet_heic_is_saved_but_not_sent_to_ai(client):
    response = client.post(
        "/api/diet/analyze",
        data={"description": "一份蔬菜沙拉", "meal_type": "dinner"},
        files={"photo": ("meal.heic", b"heic-bytes" * 8, "image/heic")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["vision_used"] is False
    assert body["photo_url"].startswith("/uploads/")
    assert "暂不支持 AI 识别" in body["note"]

    short_heic = client.post(
        "/api/diet/analyze",
        data={"meal_type": "dinner"},
        files={"photo": ("meal.heic", b"heic-bytes" * 8, "image/heic")},
    )
    assert short_heic.status_code == 422


def test_diet_vision_flag_when_deepseek_used(client, monkeypatch):
    from app.routers import diet as diet_router

    captured = {}

    async def fake_analyze(description, meal_type, profile, image=None):
        captured["image"] = image
        return (
            {
                "foods": [
                    {
                        "name": "沙拉",
                        "portion": "一份",
                        "calories": 320,
                        "protein": 12,
                        "fat": 14,
                        "carbs": 36,
                    }
                ],
                "totals": {
                    "calories": 320,
                    "protein": 12,
                    "fat": 14,
                    "carbs": 36,
                    "fiber": 6,
                    "sugar": 5,
                    "sodium": 480,
                },
                "score": 82,
                "advice": ["搭配优质蛋白"],
                "tips": ["少放沙拉酱"],
                "confidence": "high",
                "note": "基于照片与文字估算",
            },
            "deepseek",
        )

    monkeypatch.setattr(diet_router.deepseek, "analyze_diet", fake_analyze)
    response = client.post(
        "/api/diet/analyze",
        data={"meal_type": "lunch"},
        files={"photo": ("meal.jpg", b"\xff\xd8\xff" + b"0" * 32, "image/jpeg")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["vision_used"] is True
    assert body["ai_mode"] == "deepseek"
    assert captured["image"][1] == "image/jpeg"
    assert captured["image"][0].startswith(b"\xff\xd8\xff")


def test_exercise_requires_profile_then_generates(client):
    missing = client.post("/api/exercise/plan")
    assert missing.status_code == 400

    client.put(
        "/api/profile",
        json={
            "birth_year": 1998,
            "height_cm": 165,
            "weight_kg": 55,
            "activity_level": "light",
            "goal": "lose",
            "injuries": "",
        },
    )
    response = client.post("/api/exercise/plan")
    assert response.status_code == 201
    body = response.json()
    assert body["ai_mode"] == "mock"
    assert len(body["plan"]["weekly_plan"]) == 7
    assert body["metrics"]["bmi"] == 20.2
    assert body["cycle_phase"] in {
        "menstrual",
        "follicular",
        "ovulation",
        "luteal",
        "unknown",
    }

    plans = client.get("/api/exercise/plans?limit=5").json()
    assert len(plans["items"]) == 1
    assert "summary" in plans["items"][0]["plan"]


def test_finance_crud_summary_and_upsert(client):
    expense = client.post(
        "/api/finance/records",
        json={
            "record_date": "2026-11-07",
            "type": "expense",
            "amount": 25.5,
            "category": "餐饮",
            "note": "午饭",
        },
    )
    assert expense.status_code == 201
    expense_id = expense.json()["id"]

    income = client.post(
        "/api/finance/records",
        json={
            "record_date": "2026-11-01",
            "type": "income",
            "amount": 1000,
            "category": "工资",
        },
    )
    assert income.status_code == 201

    wechat = client.post(
        "/api/finance/records",
        json={
            "record_date": "2026-11-02",
            "type": "expense",
            "amount": 15,
            "category": "交通",
            "source": "wechat",
            "external_id": "wx-1",
        },
    )
    assert wechat.status_code == 201
    assert wechat.json()["source"] == "wechat"

    upsert = client.post(
        "/api/finance/records",
        json={
            "record_date": "2026-11-02",
            "type": "expense",
            "amount": 20,
            "category": "交通",
            "source": "wechat",
            "external_id": "wx-1",
        },
    )
    assert upsert.status_code == 201
    assert upsert.json()["updated"] is True
    assert upsert.json()["amount"] == 20

    records = client.get("/api/finance/records?month=2026-11").json()
    assert len(records["items"]) == 3

    summary = client.get("/api/finance/summary?month=2026-11").json()
    assert summary["income"] == 1000
    assert summary["expense"] == 45.5
    assert summary["balance"] == 954.5
    assert summary["count"] == 3
    expense_categories = [
        item for item in summary["by_category"] if item["type"] == "expense"
    ]
    assert expense_categories[0]["category"] == "餐饮"
    assert sum(item["ratio"] for item in expense_categories) == pytest.approx(1.0)

    assert client.get("/api/finance/summary?month=2026-13").status_code == 422

    deleted = client.delete(f"/api/finance/records/{expense_id}")
    assert deleted.status_code == 204
    assert client.get("/api/finance/summary?month=2026-11").json()["count"] == 2


def test_finance_validation(client):
    invalid_amount = client.post(
        "/api/finance/records",
        json={
            "record_date": "2026-11-07",
            "type": "expense",
            "amount": 0,
            "category": "餐饮",
        },
    )
    assert invalid_amount.status_code == 422

    invalid_type = client.post(
        "/api/finance/records",
        json={
            "record_date": "2026-11-07",
            "type": "transfer",
            "amount": 10,
            "category": "餐饮",
        },
    )
    assert invalid_type.status_code == 422


def test_body_records_and_weight_trend(client):
    from datetime import date, timedelta

    today = date.today()
    samples = [
        ((today - timedelta(days=14)).isoformat(), 60.0),
        ((today - timedelta(days=7)).isoformat(), 59.0),
        (today.isoformat(), 58.0),
    ]
    for record_date, weight in samples:
        response = client.post(
            "/api/body/records",
            json={
                "record_date": record_date,
                "weight_kg": weight,
                "sleep_hours": 7.5,
                "steps": 8000,
            },
        )
        assert response.status_code == 201

    summary = client.get("/api/body/summary?days=90").json()
    assert len(summary["series"]) == 3
    assert summary["latest"]["weight_kg"] == 58.0
    assert summary["weight"]["weekly_change_kg"] < 0
    assert summary["weight"]["trend"] == "下降"
    assert summary["suggestions"]
    assert client.get("/api/profile").json()["profile"]["weight_kg"] == 58.0

    records = client.get("/api/body/records").json()["items"]
    assert records[0]["weight_kg"] == 58.0

    deleted = client.delete(f"/api/body/records/{records[0]['id']}")
    assert deleted.status_code == 204
    assert len(client.get("/api/body/records").json()["items"]) == 2


def test_body_record_requires_measurement(client):
    response = client.post("/api/body/records", json={"notes": "只有备注"})
    assert response.status_code == 422


def test_exercise_screenshot_mock_and_delete(client):
    response = client.post(
        "/api/exercise/logs/analyze",
        data={"note": "今天的跑步记录"},
        files={"photo": ("run.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["ai_mode"] == "mock"
    assert len(body["records"]) == 1
    record = body["records"][0]
    assert record["source"] == "screenshot"
    assert record["activity"]
    assert record["photo_url"].startswith("/uploads/")

    photo_path = settings.upload_dir / record["photo_path"]
    assert photo_path.is_file()

    logs = client.get("/api/exercise/logs").json()["items"]
    assert len(logs) == 1

    deleted = client.delete(f"/api/exercise/logs/{record['id']}")
    assert deleted.status_code == 204
    assert not photo_path.exists()
    assert client.get("/api/exercise/logs").json()["items"] == []


def test_exercise_activity_summary(client):
    response = client.post(
        "/api/exercise/logs",
        json={
            "activity": "骑行",
            "duration_min": 45,
            "calories": 320,
            "distance_km": 12.5,
        },
    )
    assert response.status_code == 201
    summary = client.get("/api/exercise/summary?days=30").json()
    assert summary["sessions"] == 1
    assert summary["total_duration_min"] == 45
    assert summary["by_activity"][0]["activity"] == "骑行"
    assert summary["suggestions"]


def test_xiaomi_status_and_not_connected(client):
    client.post("/api/xiaomi/logout")
    status = client.get("/api/xiaomi/status").json()
    assert status["connected"] is False

    sync = client.post("/api/xiaomi/sync?days=7")
    assert sync.status_code == 400
    assert "还没有连接" in sync.json()["detail"]


def test_xiaomi_login_requires_credentials(client):
    empty = client.post("/api/xiaomi/login", json={})
    assert empty.status_code == 422


def test_diet_daily_summary_and_recommendation(client):
    from datetime import date

    today = date.today().isoformat()
    client.put(
        "/api/profile",
        json={
            "birth_year": 1998,
            "height_cm": 165,
            "weight_kg": 55,
            "activity_level": "light",
            "goal": "lose",
        },
    )
    client.post(
        "/api/diet/analyze",
        data={"description": "燕麦牛奶和一个鸡蛋", "meal_type": "breakfast", "log_date": today},
    )
    client.post(
        "/api/diet/analyze",
        data={"description": "米饭、清蒸鱼、炒青菜", "meal_type": "lunch", "log_date": today},
    )
    client.post(
        "/api/exercise/logs",
        json={"log_date": today, "activity": "快走", "duration_min": 30, "calories": 150},
    )

    daily = client.get(f"/api/diet/daily?date={today}").json()
    assert daily["date"] == today
    assert daily["totals"]["calories"] > 0
    assert len(daily["meals"]) == 2
    assert daily["recorded_meals"] == ["breakfast", "lunch"]
    assert daily["target"]["calories"] > 0
    assert abs(
        daily["remaining"]["calories"]
        - (daily["target"]["calories"] - daily["totals"]["calories"])
    ) <= 1
    assert daily["exercise"]["today"]["duration_min"] == 30
    balance = daily["energy_balance"]
    assert balance["total_burn"] == balance["tdee"] + balance["exercise_calories"]
    assert abs(balance["deficit"] - (balance["total_burn"] - daily["totals"]["calories"])) <= 1
    assert daily["suggestions"]

    response = client.post("/api/diet/recommend", json={"date": today})
    assert response.status_code == 200
    body = response.json()
    assert body["meal_type"] == "dinner"
    assert body["meal_label"] == "晚餐"
    assert body["ai_mode"] == "mock"
    recommendation = body["recommendation"]
    assert recommendation["dishes"]
    assert recommendation["exercise"]
    assert recommendation["target_calories"] > 0
    assert any("蛋白" in tip for tip in recommendation["meal_tips"])


def test_diet_daily_empty(client):
    daily = client.get("/api/diet/daily").json()
    assert daily["totals"]["calories"] == 0
    assert daily["status"] == "under"
    assert daily["suggestions"]
    assert "还没有记录" in daily["suggestions"][0]


def test_home_today_overview(client):
    from datetime import date

    today = date.today().isoformat()
    client.put(
        "/api/profile",
        json={"birth_year": 1998, "height_cm": 165, "weight_kg": 55, "goal": "lose"},
    )
    client.post(
        "/api/diet/analyze",
        data={"description": "燕麦牛奶", "meal_type": "breakfast", "log_date": today},
    )
    client.post(
        "/api/exercise/logs",
        json={"log_date": today, "activity": "快走", "duration_min": 30, "calories": 150},
    )
    client.post(
        "/api/finance/records",
        json={
            "record_date": today,
            "type": "expense",
            "amount": 25.5,
            "category": "餐饮",
        },
    )

    data = client.get(f"/api/home/today?date={today}").json()
    assert data["date"] == today
    assert data["diet"]["calories"] > 0
    assert data["diet"]["target_calories"] == 1430
    assert data["exercise"]["duration_min"] == 30
    assert data["exercise"]["calories"] == 150
    assert data["finance"]["expense"] == 25.5
    assert data["finance"]["count"] == 1
    balance = data["diet"]["energy_balance"]
    assert balance["exercise_calories"] == 150
    assert balance["total_burn"] == balance["tdee"] + 150


def test_direct_file_import_is_hidden(client):
    response = client.post(
        "/api/exercise/import",
        files={"file": ("mi.csv", b"date,steps\n2026-11-01,1000\n", "text/csv")},
    )
    assert response.status_code in (404, 405)


def test_goal_weight_and_target_date_drive_calorie_target(client):
    from datetime import date, timedelta

    target_date = (date.today() + timedelta(days=60)).isoformat()
    response = client.put(
        "/api/profile",
        json={
            "birth_year": 1998,
            "height_cm": 165,
            "weight_kg": 55,
            "activity_level": "light",
            "goal": "lose",
            "target_weight_kg": 54,
            "target_date": target_date,
        },
    )
    assert response.status_code == 200
    body = response.json()
    plan = body["metrics"]["goal_plan"]
    assert plan["has_target"] is True
    assert plan["mode"] == "lose"
    assert plan["days_left"] == 60
    assert 120 <= plan["daily_deficit"] <= 140
    assert body["profile"]["target_weight_kg"] == 54
    assert body["profile"]["target_date"] == target_date

    daily = client.get("/api/diet/daily").json()
    assert daily["target"]["method"] == "goal_plan"
    assert daily["target"]["calories"] == body["metrics"]["tdee"] - plan["daily_deficit"]
    assert daily["goal_plan"]["target_weight_kg"] == 54


def test_chat_multi_turn_memory_and_clear(client):
    first = client.post("/api/chat", json={"message": "今天晚餐吃什么？"})
    assert first.status_code == 200
    assert first.json()["reply"]
    assert len(first.json()["messages"]) == 2

    second = client.post("/api/chat", json={"message": "那蛋白质够吗？"})
    assert second.status_code == 200

    history = client.get("/api/chat/messages").json()["items"]
    assert len(history) == 4
    assert [item["role"] for item in history] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert "Mock 模式" in history[1]["content"] or history[1]["content"]

    cleared = client.delete("/api/chat/messages")
    assert cleared.status_code == 204
    assert client.get("/api/chat/messages").json()["items"] == []




def test_ai_settings_save_mask_test_and_clear(client):
    client.delete("/api/ai/settings")
    response = client.put(
        "/api/ai/settings",
        json={
            "api_key": "sk-test-12345678",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-flash",
            "vision_model": "deepseek-flash",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["api_key_masked"].endswith("5678")
    assert "sk-test-12345678" not in body["api_key_masked"]

    fetched = client.get("/api/ai/settings").json()
    assert fetched["configured"] is True
    assert fetched["base_url"] == "https://api.deepseek.com"

    tested = client.post("/api/ai/test")
    assert tested.status_code == 200
    assert tested.json()["ok"] is False

    cleared = client.delete("/api/ai/settings").json()
    assert cleared["configured"] is False


def test_exercise_description_estimates_and_affects_daily_calories(client):
    from datetime import date

    today = date.today().isoformat()
    client.put(
        "/api/profile",
        json={
            "sex": "female",
            "birth_year": 1998,
            "height_cm": 165,
            "weight_kg": 55,
            "activity_level": "light",
            "goal": "maintain",
        },
    )
    response = client.post(
        "/api/exercise/logs/describe",
        json={
            "description": "快走30分钟，然后做了20分钟力量训练",
            "log_date": today,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert len(body["records"]) == 2
    for record in body["records"]:
        assert record["source"] == "description"
        assert record["source_label"] == "文字描述"
        assert record["calories"] > 0
        assert record["calories_estimated"] is True
        assert record["calorie_basis"]
    assert body["estimated_sessions"] == 2
    assert body["estimated_calories"] > 0

    daily = client.get(f"/api/diet/daily?date={today}").json()
    exercise = daily["exercise"]["today"]
    assert exercise["sessions"] == 2
    assert exercise["calories"] == pytest.approx(
        body["estimated_calories"], abs=0.2
    )
    balance = daily["energy_balance"]
    assert balance["exercise_estimated_calories"] == pytest.approx(
        exercise["estimated_calories"], abs=0.2
    )
    assert balance["total_burn"] == pytest.approx(
        balance["tdee"] + balance["exercise_calories"], abs=0.5
    )
    assert any("估算" in suggestion for suggestion in daily["suggestions"])

    summary = client.get("/api/exercise/summary?days=30").json()
    assert summary["estimated_sessions"] == 2
    assert summary["estimated_calories"] > 0


def test_exercise_screenshot_estimates_missing_calories(client):
    from datetime import date

    client.put(
        "/api/profile",
        json={
            "sex": "female",
            "birth_year": 1998,
            "height_cm": 165,
            "weight_kg": 55,
        },
    )
    response = client.post(
        "/api/exercise/logs/analyze",
        data={"note": "手环截图"},
        files={
            "photo": (
                "run.png",
                b"\x89PNG\r\n\x1a\n" + b"0" * 64,
                "image/png",
            )
        },
    )
    assert response.status_code == 201
    body = response.json()
    record = body["records"][0]
    assert record["source"] == "screenshot"
    assert record["calories"] > 0
    assert record["calories_estimated"] is True
    assert record["calorie_basis"]
    assert body["estimated_sessions"] == 1

    today = date.today().isoformat()
    daily = client.get(f"/api/diet/daily?date={today}").json()
    assert daily["exercise"]["today"]["estimated_calories"] > 0
    assert daily["energy_balance"]["exercise_estimated_calories"] > 0


def test_exercise_description_rejects_empty(client):
    response = client.post(
        "/api/exercise/logs/describe",
        json={"description": " ", "log_date": "2026-11-07"},
    )
    assert response.status_code == 422


def test_exercise_plan_preferences_and_home_today(client):
    from datetime import date

    client.put(
        "/api/profile",
        json={
            "sex": "female",
            "birth_year": 1998,
            "height_cm": 165,
            "weight_kg": 55,
            "activity_level": "light",
            "goal": "maintain",
        },
    )
    preferences = "家里徒手训练，每周3天，每次30分钟，想减脂"
    response = client.post(
        "/api/exercise/plan",
        json={"preferences": preferences},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["preferences"] == preferences
    assert body["plan"]["preferences"] == preferences

    home = client.get("/api/home/today").json()
    plan = home["exercise_plan"]
    assert plan is not None
    assert plan["preferences"] == preferences
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
        date.today().weekday()
    ]
    assert plan["weekday"] == weekday
    assert plan["today"] is not None
    assert plan["today"]["day"] == weekday

