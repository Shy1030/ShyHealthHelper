from datetime import date

from app.exercise_estimation import (
    enrich_record,
    estimate_calories,
    parse_distance_km,
    parse_duration_minutes,
    records_from_description,
)


def test_parse_duration_variants():
    assert parse_duration_minutes("跑步 30 分钟") == 30
    assert parse_duration_minutes("1 小时 20 分钟") == 80
    assert parse_duration_minutes("半小时瑜伽") == 30
    assert parse_duration_minutes("一个半小时力量训练") == 90
    assert parse_duration_minutes("1.5 小时骑行") == 90
    assert parse_duration_minutes("40多分钟") == 45
    assert parse_duration_minutes("今天没记录时长") is None


def test_parse_distance():
    assert parse_distance_km("跑了 5 公里") == 5
    assert parse_distance_km("骑行 12.5km") == 12.5
    assert parse_distance_km("没有距离") is None


def test_estimate_with_duration_and_weight():
    result = estimate_calories("快走", 30, 55)
    assert result["activity"] == "快走"
    assert result["duration_min"] == 30
    assert result["duration_estimated"] is False
    assert result["calories_estimated"] is True
    assert 115 <= result["calories"] <= 135
    assert "MET" in result["calorie_basis"]


def test_estimate_duration_from_distance():
    result = estimate_calories("跑步", None, 55, distance_km=5)
    assert result["duration_estimated"] is True
    assert result["duration_min"] > 30
    assert result["calories"] > 250


def test_estimate_from_steps_falls_back_to_walking():
    result = estimate_calories("运动", None, 60, steps=8000)
    assert result["activity"] == "运动"
    assert result["duration_estimated"] is True
    assert result["calories"] > 200


def test_enrich_record_keeps_existing_calories():
    record = {"activity": "跑步", "duration_min": 30, "calories": 280}
    enriched = enrich_record(record, 55)
    assert enriched["calories"] == 280
    assert enriched["calories_estimated"] is False


def test_records_from_description_splits_multiple_activities():
    records = records_from_description(
        "快走30分钟，然后做了20分钟力量训练", date(2026, 11, 7), 55
    )
    assert len(records) == 2
    activities = {record["activity"] for record in records}
    assert activities == {"快走", "力量训练"}
    assert all(record["calories"] > 0 for record in records)
    assert all(record["calories_estimated"] for record in records)
    assert all(record["log_date"] == "2026-11-07" for record in records)


def test_records_from_description_distance_only():
    records = records_from_description("今天跑步5公里", date(2026, 11, 7), 55)
    assert len(records) == 1
    assert records[0]["activity"] == "跑步"
    assert records[0]["distance_km"] == 5
    assert records[0]["duration_estimated"] is True
    assert records[0]["calories"] > 250
