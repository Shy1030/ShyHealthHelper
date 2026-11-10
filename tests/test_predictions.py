from __future__ import annotations

import base64
from datetime import date, timedelta

from app.deepseek import _extract_json, _normalize_diet, _user_content
from app.predictions import analyze_cycles, build_calendar


def make_periods(starts: list[date], period_length: int = 5) -> list[dict]:
    return [
        {
            "id": index + 1,
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=period_length - 1)).isoformat(),
            "flow": "medium",
            "symptoms": "",
            "notes": "",
        }
        for index, start in enumerate(starts)
    ]


def regular_starts() -> list[date]:
    first = date(2026, 4, 4)
    return [first + timedelta(days=28 * index) for index in range(8)]


def test_no_data():
    result = analyze_cycles([], date(2026, 11, 7))
    assert result["has_data"] is False
    assert result["current"]["phase"] == "unknown"
    assert result["prediction"]["confidence"] == "insufficient"
    assert result["prediction"]["next_period_start"] is None
    assert result["reminders"][0]["type"] == "record"


def test_regular_cycle_prediction():
    today = date(2026, 11, 7)
    result = analyze_cycles(make_periods(regular_starts()), today)
    prediction = result["prediction"]
    current = result["current"]

    assert result["has_data"] is True
    assert prediction["average_cycle_length"] == 28
    assert prediction["median_cycle_length"] == 28
    assert prediction["average_period_length"] == 5
    assert prediction["cycles_used"] == 6
    assert prediction["confidence"] == "high"
    assert prediction["next_period_start"] == "2026-11-14"
    assert prediction["next_period_end"] == "2026-11-18"
    assert prediction["ovulation_date"] == "2026-10-31"
    assert prediction["fertile_window_start"] == "2026-10-26"
    assert prediction["fertile_window_end"] == "2026-11-01"
    assert len(prediction["upcoming_periods"]) == 3

    assert current["cycle_day"] == 22
    assert current["phase"] == "luteal"
    assert current["days_until_next_period"] == 7
    assert current["is_period_expected"] is True
    assert current["is_period_late"] is False

    assert any(reminder["type"] == "period" for reminder in result["reminders"])
    assert len(result["history"]) == 8
    assert result["history"][0]["cycle_length"] == 28


def test_irregular_cycle_confidence():
    starts = [date(2026, 1, 1)]
    for length in (26, 34, 27, 33, 28):
        starts.append(starts[-1] + timedelta(days=length))
    result = analyze_cycles(make_periods(starts), starts[-1] + timedelta(days=20))
    prediction = result["prediction"]
    assert prediction["average_cycle_length"] == 30
    assert prediction["confidence"] == "medium"
    assert 3.0 <= prediction["cycle_variability"] <= 3.6


def test_late_period_reminder():
    starts = regular_starts()
    result = analyze_cycles(make_periods(starts), date(2026, 11, 19))
    current = result["current"]
    assert current["is_period_late"] is True
    assert current["late_days"] == 5
    assert current["days_until_next_period"] == -5
    late = [item for item in result["reminders"] if item["type"] == "late"]
    assert late and late[0]["level"] == "warn"


def test_calendar_flags():
    starts = regular_starts()
    today = date(2026, 11, 7)
    periods = make_periods(starts)
    analysis = analyze_cycles(periods, today)
    calendar = build_calendar(2026, 11, periods, analysis, today)
    days = {item["date"]: item for item in calendar["days"]}

    assert calendar["first_weekday"] == 6
    assert days["2026-11-14"]["predicted"] is True
    assert days["2026-11-18"]["predicted"] is True
    assert days["2026-11-28"]["ovulation"] is True
    assert days["2026-11-24"]["fertile"] is True
    assert days["2026-11-07"]["is_today"] is True


def test_open_period_is_marked_actual():
    starts = [date(2026, 11, 5)]
    periods = [{"id": 1, "start_date": "2026-11-05", "end_date": None}]
    analysis = analyze_cycles(periods, date(2026, 11, 7))
    assert analysis["last_period"]["ongoing"] is True
    assert analysis["current"]["phase"] == "menstrual"

    calendar = build_calendar(2026, 11, periods, analysis, date(2026, 11, 7))
    days = {item["date"]: item for item in calendar["days"]}
    assert days["2026-11-05"]["actual"] is True
    assert days["2026-11-07"]["actual"] is True
    assert days["2026-11-08"]["actual"] is False


def test_extract_json_handles_code_fence():
    assert _extract_json('```json\n{"score": 80}\n```') == {"score": 80}
    assert _extract_json('说明文字 {"a": 1} 结束') == {"a": 1}


def test_user_content_with_vision_image():
    content = _user_content("看看这餐", (b"image-bytes", "image/png"))
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "看看这餐"}
    url = content[1]["image_url"]["url"]
    prefix = "data:image/png;base64,"
    assert url.startswith(prefix)
    assert base64.b64decode(url[len(prefix) :]) == b"image-bytes"
    assert content[1]["image_url"]["detail"] == "auto"

    assert _user_content("只有文字", None) == "只有文字"
    assert _user_content("HEIC", (b"data", "image/heic")) == "HEIC"


def test_normalize_diet_fills_totals():
    analysis = _normalize_diet(
        {
            "foods": [
                {"name": "米饭", "portion": "一碗", "calories": 200, "protein": 4, "fat": 1, "carbs": 45}
            ],
            "score": 88,
            "advice": ["搭配蔬菜"],
            "tips": ["多喝水"],
        },
        "米饭",
    )
    assert analysis["totals"]["calories"] == 200
    assert analysis["totals"]["carbs"] == 45
    assert analysis["score"] == 88
    assert analysis["advice"] == ["搭配蔬菜"]


def test_irregular_cycle_fit_fields():
    starts = [date(2026, 1, 1)]
    for length in (26, 34, 27, 33, 28):
        starts.append(starts[-1] + timedelta(days=length))
    result = analyze_cycles(make_periods(starts), starts[-1] + timedelta(days=10))
    prediction = result["prediction"]
    assert prediction["fit_method"] == "linear_fit"
    assert prediction["irregular"] is True
    assert prediction["cycle_trend"] == "stable"
    assert prediction["cycle_range_min"] == 26
    assert prediction["cycle_range_max"] == 34
    assert prediction["prediction_window_start"] < prediction["next_period_start"]
    assert prediction["prediction_window_end"] > prediction["next_period_start"]
    assert any(item["type"] == "irregular" for item in result["reminders"])


def test_regular_cycle_not_irregular():
    result = analyze_cycles(make_periods(regular_starts()), date(2026, 11, 7))
    prediction = result["prediction"]
    assert prediction["irregular"] is False
    assert prediction["cycle_trend"] == "stable"
    assert prediction["predicted_cycle_length"] == 28
