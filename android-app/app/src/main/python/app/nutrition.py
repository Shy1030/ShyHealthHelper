"""按日汇总饮食、计算热量目标，并推断下一餐。"""

from __future__ import annotations

from datetime import date, datetime

MEAL_ORDER = ("breakfast", "lunch", "dinner", "snack")
MEAL_LABELS = {
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
    "snack": "加餐",
}
NUTRIENTS = ("calories", "protein", "fat", "carbs", "fiber", "sugar", "sodium")

GOAL_ADJUSTMENTS = {"lose": -400, "maintain": 0, "gain": 300}
WEIGHT_FACTORS = {"lose": 26, "maintain": 30, "gain": 34}


def _round(value: float | None, digits: int = 1) -> float | None:
    return round(value, digits) if value is not None else None


def infer_next_meal(logs: list[dict], now: datetime | None = None) -> str:
    now = now or datetime.now()
    recorded = {log.get("meal_type") for log in logs}
    hour = now.hour
    if hour < 11 and "breakfast" not in recorded:
        return "breakfast"
    if hour < 16 and "lunch" not in recorded:
        return "lunch"
    if "dinner" not in recorded:
        return "dinner"
    return "snack"


def compute_targets(profile: dict, metrics: dict) -> dict:
    sex = profile.get("sex") or "female"
    goal = profile.get("goal") or "maintain"
    tdee = metrics.get("tdee")
    bmr = metrics.get("bmr")
    if not tdee and bmr:
        tdee = round(bmr * 1.375)
    if not tdee:
        tdee = 2200 if sex == "male" else 1800

    weight = profile.get("weight_kg")
    floor = 1500 if sex == "male" else 1200
    plan = metrics.get("goal_plan") or {}
    clamped = False
    if (
        plan.get("has_target")
        and plan.get("daily_energy_delta") is not None
        and (plan.get("days_left") or 0) > 0
    ):
        target_calories = int(round(tdee - plan["daily_energy_delta"]))
        method = "goal_plan"
        if target_calories < floor:
            target_calories = floor
            clamped = True
        required_delta = plan["daily_energy_delta"]
    elif weight:
        factor = WEIGHT_FACTORS.get(goal, 30)
        target_calories = max(floor, int(round(weight * factor)))
        method = "weight_goal"
        required_delta = None
    else:
        adjustment = GOAL_ADJUSTMENTS.get(goal, 0)
        target_calories = max(floor, int(round(tdee + adjustment)))
        method = "tdee_goal"
        required_delta = None

    if weight:
        protein_factor = 1.6 if goal in {"lose", "gain"} else 1.2
        protein_target = max(40.0, weight * protein_factor)
    else:
        protein_target = target_calories * 0.20 / 4

    fat_target = target_calories * 0.25 / 9
    carbs_target = max(0.0, (target_calories - protein_target * 4 - fat_target * 9) / 4)

    return {
        "calories": target_calories,
        "protein": round(protein_target),
        "fat": round(fat_target),
        "carbs": round(carbs_target),
        "fiber": 25,
        "tdee": int(tdee),
        "weight_kg": weight,
        "goal": goal,
        "method": method,
        "goal_plan": plan,
        "required_daily_delta": required_delta,
        "clamped": clamped,
    }


def empty_totals() -> dict:
    return {key: 0.0 for key in NUTRIENTS}


def daily_summary(
    logs: list[dict],
    profile: dict,
    metrics: dict,
    exercise_today: dict,
    exercise_recent: dict,
    target_date: date | None = None,
) -> dict:
    target_date = target_date or date.today()
    totals = empty_totals()
    meals: dict[str, dict] = {}
    for log in logs:
        meal_type = log.get("meal_type") or "snack"
        bucket = meals.setdefault(
            meal_type,
            {"meal_type": meal_type, "label": MEAL_LABELS.get(meal_type, "用餐"), "count": 0, "calories": 0.0},
        )
        bucket["count"] += 1
        for nutrient in NUTRIENTS:
            try:
                value = float(log.get(nutrient) or 0)
            except (TypeError, ValueError):
                value = 0.0
            totals[nutrient] += value
        bucket["calories"] += float(log.get("calories") or 0)

    target = compute_targets(profile, metrics)
    remaining = {
        "calories": round(target["calories"] - totals["calories"]),
        "protein": round(target["protein"] - totals["protein"]),
        "fat": round(target["fat"] - totals["fat"]),
        "carbs": round(target["carbs"] - totals["carbs"]),
    }

    if totals["calories"] > target["calories"] * 1.05:
        status = "over"
        status_label = "已超出"
    elif remaining["calories"] > max(150, target["calories"] * 0.15):
        status = "under"
        status_label = "还有余量"
    else:
        status = "on_track"
        status_label = "接近目标"

    suggestions: list[str] = []
    if not logs:
        suggestions.append("还没有记录今天的饮食，先记录早餐或午餐，才能计算剩余热量。")
    else:
        next_meal = infer_next_meal(logs)
        meal_label = MEAL_LABELS[next_meal]
        if remaining["calories"] > 0:
            suggestions.append(
                f"今日还可摄入约 {remaining['calories']} 千卡，{meal_label}建议控制在 "
                f"{max(250, min(700, remaining['calories']))} 千卡以内。"
            )
        else:
            suggestions.append(
                f"今日热量已超出目标约 {-remaining['calories']} 千卡，下一餐建议清淡、少油少糖。"
            )
        if remaining["protein"] > 20:
            suggestions.append(
                f"蛋白质还差约 {remaining['protein']} g，可优先选择鱼虾、鸡蛋、瘦肉、豆制品或酸奶。"
            )
        if totals["sodium"] > 2400:
            suggestions.append("今日钠摄入偏高，下一餐少放盐和酱料，多喝水。")
        if totals["fiber"] < 15 and logs:
            suggestions.append("膳食纤维偏少，建议增加一份深色蔬菜或低糖水果。")
        missing = [MEAL_LABELS[m] for m in MEAL_ORDER[:3] if m not in meals]
        if missing:
            suggestions.append(f"今天还没记录：{'、'.join(missing)}，补录后热量统计会更准确。")

    tdee = int(metrics.get("tdee") or target.get("tdee") or target["calories"])
    exercise_calories = float(exercise_today.get("calories") or 0)
    exercise_estimated_calories = float(
        exercise_today.get("estimated_calories") or 0
    )
    total_burn = int(round(tdee + exercise_calories))
    deficit = int(round(total_burn - totals["calories"]))
    if deficit > 100:
        balance_status, balance_label = "deficit", "热量缺口"
    elif deficit < -100:
        balance_status, balance_label = "surplus", "热量盈余"
    else:
        balance_status, balance_label = "balanced", "基本平衡"

    if deficit > 700:
        suggestions.append(
            f"今日热量缺口约 {deficit} 千卡，缺口偏大。长期过大可能影响代谢和恢复，"
            "建议保证蛋白质和主食，不要用极端节食换体重下降。"
        )
    elif deficit < -300:
        suggestions.append(
            f"今日热量盈余约 {-deficit} 千卡，可通过饭后散步或下一餐减量来平衡。"
        )

    today_minutes = float(exercise_today.get("duration_min") or 0)
    if today_minutes >= 30:
        suggestions.append(
            f"今天已运动 {int(today_minutes)} 分钟，注意补充蛋白质和水分，晚餐不必额外节食。"
        )
    elif today_minutes > 0:
        suggestions.append(f"今天已运动 {int(today_minutes)} 分钟，饭后可以再散步 15-20 分钟。")
    else:
        suggestions.append("今天还没有运动记录，饭后快走 20-30 分钟有助于血糖和热量平衡。")
    if exercise_estimated_calories > 0:
        suggestions.append(
            f"今日运动消耗中约 {int(round(exercise_estimated_calories))} 千卡来自估算，"
            "如果有手环或运动 App 数据，可以补录截图提高准确性。"
        )

    return {
        "date": target_date.isoformat(),
        "totals": {key: round(value, 1) for key, value in totals.items()},
        "meals": [meals[key] for key in MEAL_ORDER if key in meals],
        "recorded_meals": [m for m in MEAL_ORDER if m in meals],
        "target": target,
        "remaining": remaining,
        "status": status,
        "status_label": status_label,
        "progress": round(min(1.5, totals["calories"] / max(1, target["calories"])), 3),
        "exercise": {
            "today": exercise_today,
            "recent": exercise_recent,
        },
        "goal_plan": target.get("goal_plan") or {},
        "energy_balance": {
            "intake": round(totals["calories"], 1),
            "tdee": tdee,
            "exercise_calories": round(exercise_calories, 1),
            "exercise_estimated_calories": round(exercise_estimated_calories, 1),
            "total_burn": total_burn,
            "deficit": deficit,
            "status": balance_status,
            "status_label": balance_label,
            "target_daily_delta": target.get("required_daily_delta"),
            "target_method": target.get("method"),
            "note": "TDEE 已包含日常活动，运动消耗（含估算）按额外训练叠加，仅作参考。",
        },
        "suggestions": suggestions[:6],
    }
