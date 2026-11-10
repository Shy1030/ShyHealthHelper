"""长期体重 / 身体数据的趋势分析与规则建议。

不依赖 AI，Mock 模式下也能给出稳定、可解释的建议；所有结论仅作健康管理参考。
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import mean


def _round(value: float | None, digits: int = 1) -> float | None:
    return round(value, digits) if value is not None else None


def _numeric(records: list[dict], key: str) -> list[tuple[date, float]]:
    points: list[tuple[date, float]] = []
    for record in records:
        value = record.get(key)
        if value is None:
            continue
        try:
            points.append((date.fromisoformat(str(record["record_date"])[:10]), float(value)))
        except (TypeError, ValueError):
            continue
    points.sort(key=lambda item: item[0])
    return points


def _linear_slope(points: list[tuple[date, float]]) -> float | None:
    """返回每天的变化量（最小二乘）。"""
    if len(points) < 2:
        return None
    origin = points[0][0]
    xs = [(point_date - origin).days for point_date, _ in points]
    ys = [value for _, value in points]
    mean_x = mean(xs)
    mean_y = mean(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator


def _value_before(points: list[tuple[date, float]], days: int, today: date) -> float | None:
    cutoff = today - timedelta(days=days)
    candidates = [value for point_date, value in points if point_date <= cutoff]
    return candidates[-1] if candidates else None


def _average_recent(points: list[tuple[date, float]], days: int, today: date) -> float | None:
    cutoff = today - timedelta(days=days)
    values = [value for point_date, value in points if cutoff <= point_date <= today]
    return mean(values) if values else None


def _trend_label(weekly_change: float | None) -> str:
    if weekly_change is None:
        return "数据不足"
    if weekly_change <= -0.15:
        return "下降"
    if weekly_change >= 0.15:
        return "上升"
    return "基本稳定"


def _healthy_weight_range(height_cm: float | None) -> tuple[float, float] | None:
    if not height_cm:
        return None
    height_m = height_cm / 100
    return (round(18.5 * height_m * height_m, 1), round(24 * height_m * height_m, 1))


def _bmi_category(bmi: float | None) -> str:
    if bmi is None:
        return "未知"
    if bmi < 18.5:
        return "偏低"
    if bmi < 24:
        return "正常"
    if bmi < 28:
        return "偏高"
    return "肥胖"


def analyze_body_records(
    records: list[dict],
    profile: dict,
    metrics: dict,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    clean: list[dict] = []
    for record in records:
        try:
            record_date = date.fromisoformat(str(record["record_date"])[:10])
        except (KeyError, TypeError, ValueError):
            continue
        if record_date > today:
            continue
        clean.append({**record, "record_date": record_date.isoformat()})
    clean.sort(key=lambda item: item["record_date"])

    weights = _numeric(clean, "weight_kg")
    body_fats = _numeric(clean, "body_fat_pct")
    sleeps = _numeric(clean, "sleep_hours")
    steps = _numeric(clean, "steps")
    resting = _numeric(clean, "resting_hr")

    latest_weight = weights[-1][1] if weights else None
    latest_body_fat = body_fats[-1][1] if body_fats else None
    latest_date = weights[-1][0] if weights else (
        date.fromisoformat(clean[-1]["record_date"]) if clean else None
    )

    slope_per_day = _linear_slope(weights)
    weekly_change = _round(slope_per_day * 7, 2) if slope_per_day is not None else None
    total_change = (
        _round(latest_weight - weights[0][1], 2) if len(weights) >= 2 else None
    )
    days_tracked = (weights[-1][0] - weights[0][0]).days if len(weights) >= 2 else 0

    change_7d = None
    change_30d = None
    if weights:
        before_7 = _value_before(weights, 7, today)
        before_30 = _value_before(weights, 30, today)
        change_7d = _round(latest_weight - before_7, 2) if before_7 is not None else None
        change_30d = _round(latest_weight - before_30, 2) if before_30 is not None else None

    height = profile.get("height_cm")
    bmi = metrics.get("bmi")
    if bmi is None and height and latest_weight:
        bmi = round(latest_weight / ((height / 100) ** 2), 1)
    healthy_range = _healthy_weight_range(height)
    goal = profile.get("goal") or "maintain"

    avg_sleep = _average_recent(sleeps, 14, today)
    avg_steps = _average_recent(steps, 14, today)
    avg_resting = _average_recent(resting, 14, today)

    suggestions: list[str] = []
    if len(weights) < 2:
        suggestions.append(
            "体重记录还不足 2 次。建议固定在早晨空腹、排空后测量，每周至少记录 2-3 次。"
        )
    else:
        if goal == "lose":
            if weekly_change is not None and weekly_change < -0.8:
                suggestions.append(
                    f"近阶段每周约下降 {abs(weekly_change):.2f} kg，速度偏快。"
                    "建议适当增加主食和蛋白质，避免肌肉流失与代谢下降。"
                )
            elif weekly_change is not None and weekly_change > 0.2:
                suggestions.append(
                    f"体重近阶段每周上升约 {weekly_change:.2f} kg，与减脂目标不一致。"
                    "建议复盘饮食份量与含糖饮料，并把每周有氧增加到 150 分钟以上。"
                )
            elif weekly_change is not None:
                suggestions.append(
                    "减脂速度处于合理范围，继续保持规律饮食与每周 2-3 次力量训练。"
                )
        elif goal == "gain":
            if weekly_change is not None and weekly_change < 0.1:
                suggestions.append(
                    "体重增长较慢。增肌需要温和的热量盈余，可在训练后补充蛋白质与主食。"
                )
            elif weekly_change is not None and weekly_change > 0.5:
                suggestions.append(
                    f"体重每周增长约 {weekly_change:.2f} kg，速度偏快，脂肪增加可能较多。"
                    "建议放慢增重速度，并保证力量训练强度。"
                )
            else:
                suggestions.append("增重速度较平稳，建议保证蛋白质摄入并持续力量训练。")
        else:
            if abs(weekly_change or 0) <= 0.3:
                suggestions.append("体重总体稳定，继续保持规律作息与均衡饮食。")
            elif (weekly_change or 0) > 0:
                suggestions.append("体重缓慢上升，如非刻意增重，可适当减少精制碳水与夜宵。")
            else:
                suggestions.append("体重缓慢下降，如精力与睡眠正常，通常无需特别担心。")

        if change_7d is not None and abs(change_7d) >= 1.5:
            suggestions.append(
                f"最近 7 天体重波动约 {change_7d:+.1f} kg，短期波动多与水分、盐分和经期相关，"
                "建议看 7 天平均值而不是单日数字。"
            )

    if bmi is not None:
        category = _bmi_category(bmi)
        if category in {"偏高", "肥胖"}:
            suggestions.append(
                f"当前 BMI {bmi}（{category}）。建议以每周 0.5-0.8 kg 的速度减脂，"
                "结合快走、骑行与力量训练，避免极端节食。"
            )
        elif category == "偏低":
            suggestions.append(
                f"当前 BMI {bmi}（偏低）。建议增加优质蛋白、坚果和奶类，并配合力量训练增肌。"
            )
    elif healthy_range:
        suggestions.append(
            f"按身高计算，健康体重范围约 {healthy_range[0]}-{healthy_range[1]} kg。"
        )

    if latest_body_fat is not None:
        sex = profile.get("sex") or "female"
        high = 32 if sex != "male" else 25
        if latest_body_fat >= high:
            suggestions.append(
                f"体脂率约 {latest_body_fat:.1f}%，偏高。建议增加力量训练与蛋白质，"
                "同时控制精制糖和油炸食品。"
            )

    if avg_sleep is not None and avg_sleep < 7:
        suggestions.append(
            f"近两周平均睡眠约 {avg_sleep:.1f} 小时，偏少。睡眠不足会影响食欲激素与恢复，"
            "建议尽量保证 7-9 小时。"
        )
    if avg_steps is not None and avg_steps < 6000:
        suggestions.append(
            f"近两周平均步数约 {int(avg_steps)} 步，偏少。可以先从每天多走 1500-2000 步开始。"
        )
    if avg_resting is not None and avg_resting >= 80:
        suggestions.append(
            f"近两周平均静息心率约 {int(avg_resting)} 次/分，偏高。若伴随疲劳或睡眠变差，"
            "建议减少高强度训练并留意恢复。"
        )

    if not suggestions:
        suggestions.append("数据看起来比较平稳，继续保持记录，趋势会越来越准确。")

    series = [
        {
            "date": record["record_date"],
            "weight_kg": record.get("weight_kg"),
            "body_fat_pct": record.get("body_fat_pct"),
            "muscle_kg": record.get("muscle_kg"),
            "waist_cm": record.get("waist_cm"),
            "sleep_hours": record.get("sleep_hours"),
            "resting_hr": record.get("resting_hr"),
            "steps": record.get("steps"),
            "source": record.get("source", "manual"),
        }
        for record in clean
    ]

    headline = "还没有体重数据，先记录一次吧。"
    if latest_weight is not None:
        parts = [f"最新体重 {latest_weight:.1f} kg"]
        if weekly_change is not None:
            parts.append(f"每周 {weekly_change:+.2f} kg（{_trend_label(weekly_change)}）")
        if total_change is not None:
            parts.append(f"累计 {total_change:+.1f} kg / {days_tracked} 天")
        headline = "，".join(parts)

    return {
        "today": today.isoformat(),
        "headline": headline,
        "tracked_days": days_tracked,
        "record_count": len(clean),
        "weight_count": len(weights),
        "latest": {
            "date": latest_date.isoformat() if latest_date else None,
            "weight_kg": _round(latest_weight),
            "body_fat_pct": _round(latest_body_fat),
            "bmi": bmi,
            "bmi_category": _bmi_category(bmi),
            "healthy_weight_range": (
                {"min": healthy_range[0], "max": healthy_range[1]}
                if healthy_range
                else None
            ),
        },
        "weight": {
            "trend": _trend_label(weekly_change),
            "weekly_change_kg": weekly_change,
            "total_change_kg": total_change,
            "change_7d": change_7d,
            "change_30d": change_30d,
            "goal": goal,
        },
        "averages": {
            "sleep_hours": _round(avg_sleep),
            "steps": int(avg_steps) if avg_steps is not None else None,
            "resting_hr": int(avg_resting) if avg_resting is not None else None,
        },
        "suggestions": suggestions[:8],
        "series": series,
    }
