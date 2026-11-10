"""运动热量估算：MET 公式、缺失时长推断与自然语言描述解析。

用于两类场景：
1. 截图/文字记录里没有热量时，按体重、运动类型、时长自动估算；
2. Mock 模式或 AI 未返回可用记录时，作为本地兜底解析。
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

DEFAULT_WEIGHT_KG = 60.0

# MET（代谢当量）参考值，单位：千卡/公斤/小时
MET_TABLE: dict[str, float] = {
    "跑步": 9.0,
    "快走": 4.3,
    "走路": 3.5,
    "骑行": 7.5,
    "游泳": 8.0,
    "跳绳": 11.0,
    "力量训练": 5.0,
    "HIIT": 10.0,
    "瑜伽": 3.0,
    "普拉提": 3.0,
    "跳操": 6.5,
    "舞蹈": 6.0,
    "篮球": 8.0,
    "足球": 7.0,
    "羽毛球": 5.5,
    "网球": 7.3,
    "爬山": 6.5,
    "徒步": 6.0,
    "椭圆机": 7.0,
    "划船": 7.0,
    "拉伸": 2.3,
    "家务": 3.3,
    "运动": 5.0,
}

# 用于从自然语言中识别运动类型，按“越具体越靠前”排序
ACTIVITY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("跳绳", ("跳绳", "跳神", "jump rope")),
    ("HIIT", ("hiit", "高强度间歇", "间歇训练", "tabata")),
    ("力量训练", ("力量训练", "撸铁", "举铁", "深蹲", "硬拉", "卧推", "俯卧撑", "核心训练")),
    ("普拉提", ("普拉提", "pilates")),
    ("瑜伽", ("瑜伽", "yoga")),
    ("跳操", ("跳操", "健身操", "有氧操", "帕梅拉")),
    ("舞蹈", ("舞蹈", "跳舞", "zumba")),
    ("椭圆机", ("椭圆机",)),
    ("划船", ("划船", "划船机", "rowing")),
    ("游泳", ("游泳", "swim")),
    ("骑行", ("骑行", "骑车", "自行车", "单车", "动感单车", "cycling", "bike")),
    ("快走", ("快走", "健走", "brisk walk")),
    ("爬山", ("爬山", "登山", "hiking")),
    ("徒步", ("徒步", "hiking")),
    ("篮球", ("篮球", "basketball")),
    ("足球", ("足球", "football", "soccer")),
    ("羽毛球", ("羽毛球", "badminton")),
    ("网球", ("网球", "tennis")),
    ("乒乓球", ("乒乓球",)),
    ("跑步", ("跑步", "慢跑", "跑了", "晨跑", "夜跑", "jogging", "running", " run")),
    ("拉伸", ("拉伸", "拉伸放松", "stretch")),
    ("家务", ("家务", "打扫", "拖地", "清洁")),
    ("走路", ("走路", "散步", "步行", "走了", "遛弯", "walk")),
]

ACTIVITY_ALIASES: dict[str, str] = {
    "慢跑": "跑步",
    "跑步机": "跑步",
    "散步": "走路",
    "步行": "走路",
    "骑车": "骑行",
    "自行车": "骑行",
    "单车": "骑行",
    "动感单车": "骑行",
    "登山": "爬山",
    "撸铁": "力量训练",
    "举铁": "力量训练",
    "健身操": "跳操",
    "有氧操": "跳操",
    "跳舞": "舞蹈",
    "间歇训练": "HIIT",
    "高强度间歇": "HIIT",
}

DEFAULT_DURATION_MIN: dict[str, float] = {
    "跳绳": 15,
    "HIIT": 20,
    "力量训练": 40,
    "普拉提": 40,
    "瑜伽": 40,
    "跳操": 30,
    "舞蹈": 40,
    "椭圆机": 30,
    "划船": 30,
    "游泳": 30,
    "骑行": 40,
    "快走": 40,
    "爬山": 90,
    "徒步": 90,
    "篮球": 60,
    "足球": 60,
    "羽毛球": 45,
    "网球": 60,
    "乒乓球": 45,
    "跑步": 30,
    "拉伸": 15,
    "家务": 30,
    "走路": 30,
    "运动": 30,
}

# 无时长但有距离时，按常见配速反推时长（km/h）
DISTANCE_SPEED_KMH: dict[str, float] = {
    "跑步": 9.0,
    "快走": 5.5,
    "走路": 4.5,
    "骑行": 18.0,
    "游泳": 2.5,
    "爬山": 3.5,
    "徒步": 4.0,
    "运动": 6.0,
}

INTENSITY_FACTORS = {"low": 0.9, "moderate": 1.0, "high": 1.12}
INTENSITY_LABELS = {"low": "低强度", "moderate": "中强度", "high": "高强度"}

CN_NUMBERS = {
    "零": 0,
    "一": 1,
    "两": 2,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "是", "已估算"}
    return bool(value)


def normalize_activity(activity: Any) -> str:
    text = str(activity or "").strip()
    if not text:
        return "运动"
    if text in MET_TABLE:
        return text
    if text in ACTIVITY_ALIASES:
        return ACTIVITY_ALIASES[text]
    lowered = text.lower()
    for name, keywords in ACTIVITY_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return name
    return "运动"


def detect_activity(text: Any) -> str:
    return normalize_activity(text)


def _looks_like_activity(text: str) -> bool:
    lowered = text.lower()
    return any(
        keyword in lowered for _, keywords in ACTIVITY_KEYWORDS for keyword in keywords
    )


def parse_duration_minutes(text: str) -> float | None:
    """从中文/英文描述中解析分钟数，例如 30分钟、1小时20分钟、一个半小时。"""
    if not text:
        return None
    total = 0.0
    found = False

    hour_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:个)?\s*(?:半)?\s*(?:小时|h|hr|hrs|hours)", text
    )
    if hour_match:
        hours = float(hour_match.group(1))
        if "半" in hour_match.group(0):
            hours += 0.5
        total += hours * 60
        found = True
    else:
        cn_match = re.search(
            r"([一两二三四五六七八九十])\s*(?:个)?\s*(?:半)?\s*(?:小时|h)", text
        )
        if cn_match:
            hours = CN_NUMBERS.get(cn_match.group(1), 0)
            if "半" in cn_match.group(0):
                hours += 0.5
            total += hours * 60
            found = True
        elif re.search(r"([一两二三四五六七八九十])\s*小时\s*半", text):
            match = re.search(r"([一两二三四五六七八九十])\s*小时\s*半", text)
            total += (CN_NUMBERS.get(match.group(1), 0) + 0.5) * 60
            found = True
        elif "半小时" in text:
            total += 30
            found = True

    minute_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:多)?\s*(?:分钟|min|mins|minutes)", text
    )
    if minute_match:
        minutes = float(minute_match.group(1))
        if "多" in minute_match.group(0):
            minutes += 5
        total += minutes
        found = True

    if not found or total <= 0:
        return None
    return round(total, 1)


def parse_distance_km(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:公里|千米|km)", text or "", re.IGNORECASE)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return round(value, 2) if 0 < value < 2000 else None


def parse_steps(text: str) -> int | None:
    match = re.search(r"(\d{2,6})\s*步", text or "")
    if not match:
        return None
    value = int(match.group(1))
    return value if 0 < value <= 300000 else None


def _duration_from_distance(activity: str, distance_km: float) -> float:
    speed = DISTANCE_SPEED_KMH.get(activity, 6.0)
    return round(distance_km / speed * 60, 1)


def estimate_calories(
    activity: Any,
    duration_min: float | None = None,
    weight_kg: float | None = None,
    intensity: str | None = None,
    distance_km: float | None = None,
    steps: int | None = None,
) -> dict:
    """按 MET 估算热量，缺失时长会按距离/步数/常见习惯推断。"""
    name = normalize_activity(activity)
    weight = float(weight_kg) if weight_kg else DEFAULT_WEIGHT_KG
    weight = max(25.0, min(300.0, weight))
    duration = float(duration_min) if duration_min and duration_min > 0 else None
    duration_estimated = False
    distance = float(distance_km) if distance_km and distance_km > 0 else None
    step_count = int(steps) if steps and steps > 0 else None

    if duration is None and distance:
        duration = _duration_from_distance(name, distance)
        duration_estimated = True
    if duration is None and step_count:
        step_length = 0.9 if name in {"跑步", "快走"} else 0.75
        distance = step_count * step_length / 1000
        duration = _duration_from_distance(
            name if name in DISTANCE_SPEED_KMH else "走路", distance
        )
        duration_estimated = True
    if duration is None:
        duration = DEFAULT_DURATION_MIN.get(name, 30)
        duration_estimated = True

    duration = max(1.0, min(1440.0, duration))
    met = MET_TABLE.get(name, MET_TABLE["运动"])
    intensity_key = str(intensity or "").lower()
    met *= INTENSITY_FACTORS.get(intensity_key, 1.0)
    calories = met * 3.5 * weight / 200 * duration
    calories = round(max(5.0, min(5000.0, calories)), 1)

    basis_parts = [f"{name} MET {met:.1f}", f"{weight:.0f}kg", f"{duration:.0f}分钟"]
    if distance:
        basis_parts.append(f"{distance:.1f}km")
    if step_count:
        basis_parts.append(f"{step_count}步")
    if intensity_key in INTENSITY_LABELS:
        basis_parts.append(INTENSITY_LABELS[intensity_key])
    basis = "按 " + " · ".join(basis_parts) + " 估算"

    return {
        "activity": name,
        "duration_min": round(duration, 1),
        "duration_estimated": duration_estimated,
        "calories": calories,
        "calories_estimated": True,
        "calorie_basis": basis,
    }


def enrich_record(record: dict, weight_kg: float | None = None) -> dict:
    """补齐单条记录的热量；已有热量则保留，并统一估算标记。"""
    calories = record.get("calories")
    try:
        calories_value = float(calories) if calories is not None else 0.0
    except (TypeError, ValueError):
        calories_value = 0.0

    record["calories_estimated"] = as_bool(record.get("calories_estimated"))
    record["duration_estimated"] = as_bool(record.get("duration_estimated"))

    if calories_value > 0:
        record["calories"] = round(calories_value, 1)
        record["calorie_basis"] = str(
            record.get("calorie_basis")
            or ("记录中的热量数据" if not record["calories_estimated"] else "AI 估算")
        )[:300]
        return record

    estimate = estimate_calories(
        activity=record.get("activity"),
        duration_min=record.get("duration_min"),
        weight_kg=weight_kg,
        intensity=record.get("intensity"),
        distance_km=record.get("distance_km"),
        steps=record.get("steps"),
    )
    record["activity"] = estimate["activity"]
    record["duration_min"] = estimate["duration_min"]
    record["duration_estimated"] = estimate["duration_estimated"]
    record["calories"] = estimate["calories"]
    record["calories_estimated"] = True
    record["calorie_basis"] = estimate["calorie_basis"]
    return record


def _split_clauses(description: str) -> list[str]:
    parts = re.split(
        r"[，,。.;；!！?？\n]|然后|接着|之后|随后|再做|又做|以及|同时|另外",
        description or "",
    )
    return [part.strip() for part in parts if part and part.strip()]


def records_from_description(
    description: str,
    log_date: date | None = None,
    weight_kg: float | None = None,
) -> list[dict]:
    """把一句自然语言拆成多条运动记录并估算热量（本地兜底/Mock 模式）。"""
    target_date = (log_date or date.today()).isoformat()
    clauses = _split_clauses(description)
    records: list[dict] = []

    for clause in clauses:
        activity_text = detect_activity(clause)
        has_activity = activity_text != "运动" or _looks_like_activity(clause)
        duration = parse_duration_minutes(clause)
        distance = parse_distance_km(clause)
        steps = parse_steps(clause)

        if not has_activity:
            if (duration or distance or steps) and records:
                last = records[-1]
                if duration and not last.get("duration_min"):
                    last["duration_min"] = duration
                if distance and not last.get("distance_km"):
                    last["distance_km"] = distance
                if steps and not last.get("steps"):
                    last["steps"] = steps
            continue

        if activity_text == "运动" and steps:
            activity_text = "走路"

        estimate = estimate_calories(
            activity=activity_text,
            duration_min=duration,
            weight_kg=weight_kg,
            distance_km=distance,
            steps=steps,
        )
        records.append(
            {
                "log_date": target_date,
                "start_time": None,
                "activity": estimate["activity"],
                "duration_min": estimate["duration_min"],
                "calories": estimate["calories"],
                "distance_km": distance,
                "steps": steps,
                "avg_heart_rate": None,
                "notes": clause[:200],
                "calories_estimated": True,
                "duration_estimated": estimate["duration_estimated"],
                "calorie_basis": estimate["calorie_basis"],
            }
        )

    # 整段描述是一句话但没有逗号分隔时，再尝试整体解析一次
    if not records and description.strip():
        activity_text = detect_activity(description)
        duration = parse_duration_minutes(description)
        distance = parse_distance_km(description)
        steps = parse_steps(description)
        if (
            activity_text != "运动"
            or duration is not None
            or distance is not None
            or steps is not None
        ):
            if activity_text == "运动" and steps:
                activity_text = "走路"
            estimate = estimate_calories(
                activity=activity_text,
                duration_min=duration,
                weight_kg=weight_kg,
                distance_km=distance,
                steps=steps,
            )
            records.append(
                {
                    "log_date": target_date,
                    "start_time": None,
                    "activity": estimate["activity"],
                    "duration_min": estimate["duration_min"],
                    "calories": estimate["calories"],
                    "distance_km": distance,
                    "steps": steps,
                    "avg_heart_rate": None,
                    "notes": description.strip()[:200],
                    "calories_estimated": True,
                    "duration_estimated": estimate["duration_estimated"],
                    "calorie_basis": estimate["calorie_basis"],
                }
            )

    return records


def summarize_records(records: list[dict]) -> dict:
    total_calories = round(
        sum(float(record.get("calories") or 0) for record in records), 1
    )
    total_duration = round(
        sum(float(record.get("duration_min") or 0) for record in records), 1
    )
    estimated = [record for record in records if record.get("calories_estimated")]
    return {
        "count": len(records),
        "total_calories": total_calories,
        "total_duration_min": total_duration,
        "estimated_sessions": len(estimated),
        "estimated_calories": round(
            sum(float(record.get("calories") or 0) for record in estimated), 1
        ),
    }
