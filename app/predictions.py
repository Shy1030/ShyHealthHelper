from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import mean, median, pstdev
from typing import Any

MIN_CYCLE = 15
MAX_CYCLE = 60
DEFAULT_CYCLE = 28
DEFAULT_PERIOD = 5
MAX_CYCLES_USED = 6
FORECAST_CYCLES = 3
LUTEAL_DAYS = 14
IRREGULAR_RANGE = 8
TREND_THRESHOLD = 0.6

CYCLE_TREND_LABELS = {
    "lengthening": "周期变长",
    "shortening": "周期变短",
    "stable": "周期稳定",
    "unknown": "趋势未知",
}

PHASE_INFO: dict[str, dict[str, str]] = {
    "menstrual": {
        "label": "经期",
        "tip": "注意保暖与休息，适合散步、轻度拉伸，避免高强度训练和生冷饮食。",
    },
    "follicular": {
        "label": "卵泡期",
        "tip": "精力逐步回升，适合力量训练与有氧运动，可以循序渐进提高强度。",
    },
    "ovulation": {
        "label": "排卵期",
        "tip": "身体状态较好，可安排中高强度训练，注意补水与充分热身。",
    },
    "luteal": {
        "label": "黄体期",
        "tip": "体温略升、容易疲劳，适合中低强度运动，适当控制盐分和糖分。",
    },
    "unknown": {
        "label": "待记录",
        "tip": "记录第一次月经后即可获得周期预测与提醒。",
    },
}


def parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _fmt_cn(value: date | None) -> str:
    if value is None:
        return "暂无"
    return f"{value.month}月{value.day}日"


def _round(value: float) -> int:
    return int(value + 0.5)


def _confidence(cycles_used: int, std: float) -> tuple[str, str]:
    if cycles_used >= 6 and std <= 2:
        return "high", "高"
    if cycles_used >= 3 and std <= 4:
        return "medium", "中"
    if cycles_used >= 1:
        return "low", "低"
    return "insufficient", "数据不足"


def _linear_slope(values: list[float]) -> float | None:
    count = len(values)
    if count < 2:
        return None
    xs = list(range(count))
    mean_x = mean(xs)
    mean_y = mean(values)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values)) / denominator


def _fit_cycles(cycle_lengths: list[int]) -> dict:
    """对最近周期做线性拟合，估计下一次经期与拟合残差。"""
    if not cycle_lengths:
        return {
            "predicted_cycle": DEFAULT_CYCLE,
            "residual_std": 0.0,
            "method": "default",
        }

    offsets = [0]
    for length in cycle_lengths:
        offsets.append(offsets[-1] + length)

    if len(cycle_lengths) == 1:
        predicted_cycle = float(cycle_lengths[0])
        residuals = [0.0, 0.0]
    else:
        xs = list(range(len(offsets)))
        mean_x = mean(xs)
        mean_y = mean(offsets)
        denominator = sum((x - mean_x) ** 2 for x in xs)
        slope = (
            sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, offsets))
            / denominator
            if denominator
            else float(mean(cycle_lengths))
        )
        intercept = mean_y - slope * mean_x
        next_offset = intercept + slope * len(offsets)
        predicted_cycle = next_offset - offsets[-1]
        residuals = [
            value - (intercept + slope * x) for x, value in zip(xs, offsets)
        ]

    if not 10 <= predicted_cycle <= 90:
        predicted_cycle = float(mean(cycle_lengths))

    residual_std = pstdev(residuals) if len(residuals) > 1 else 0.0
    return {
        "predicted_cycle": predicted_cycle,
        "residual_std": residual_std,
        "method": "linear_fit",
    }


def _cycle_trend(cycle_lengths: list[int]) -> str:
    slope = _linear_slope([float(length) for length in cycle_lengths])
    if slope is None:
        return "unknown"
    if slope >= TREND_THRESHOLD:
        return "lengthening"
    if slope <= -TREND_THRESHOLD:
        return "shortening"
    return "stable"


def _build_reminders(
    today: date,
    last_start: date | None,
    last_end: date | None,
    next_start: date | None,
    fertile_start: date | None,
    fertile_end: date | None,
    days_until: int | None,
    has_data: bool,
) -> list[dict[str, str]]:
    reminders: list[dict[str, str]] = []

    if not has_data:
        reminders.append(
            {
                "type": "record",
                "level": "info",
                "title": "开始记录",
                "message": "记录第一次月经，即可获得周期预测、易孕期和提醒。",
            }
        )
        return reminders

    if days_until is not None:
        if days_until < 0:
            reminders.append(
                {
                    "type": "late",
                    "level": "warn",
                    "title": f"下次月经已推迟 {-days_until} 天",
                    "message": (
                        f"比预测晚 {-days_until} 天。如果已经来潮，请及时补录；"
                        "若长期不规律，建议咨询专业医生。"
                    ),
                }
            )
        elif days_until == 0:
            reminders.append(
                {
                    "type": "period",
                    "level": "warn",
                    "title": "预计今天来潮",
                    "message": "预测今天开始新的月经周期，请留意身体信号并提前准备卫生用品。",
                }
            )
        elif days_until <= 7:
            reminders.append(
                {
                    "type": "period",
                    "level": "info",
                    "title": f"下次月经预估还有 {days_until} 天",
                    "message": (
                        f"预计 {_fmt_cn(next_start)} 来潮，"
                        "可以提前准备卫生用品并减少熬夜。"
                    ),
                }
            )

    if fertile_start and fertile_end and last_start:
        if fertile_start <= today <= fertile_end:
            reminders.append(
                {
                    "type": "fertile",
                    "level": "info",
                    "title": "处于易孕期",
                    "message": (
                        f"当前处于易孕期（{_fmt_cn(fertile_start)} - {_fmt_cn(fertile_end)}）。"
                        "请注意避孕或合理安排备孕。"
                    ),
                }
            )
        elif 0 < (fertile_start - today).days <= 5:
            reminders.append(
                {
                    "type": "fertile",
                    "level": "info",
                    "title": "易孕期临近",
                    "message": f"预计 {_fmt_cn(fertile_start)} 进入易孕期。",
                }
            )

    if last_end and today > last_end + timedelta(days=3) and (
        last_end - last_start
    ).days + 1 > 10:
        reminders.append(
            {
                "type": "record",
                "level": "info",
                "title": "经期记录过长",
                "message": "本次经期已超过 10 天，建议补录结束日期或关注身体情况。",
            }
        )

    return reminders


def _build_reminders_with_irregular(
    today: date,
    last_start: date | None,
    last_end: date | None,
    next_start: date | None,
    fertile_start: date | None,
    fertile_end: date | None,
    days_until: int | None,
    irregular: bool,
    variability: float,
) -> list[dict[str, str]]:
    reminders = _build_reminders(
        today,
        last_start,
        last_end,
        next_start,
        fertile_start,
        fertile_end,
        days_until,
        True,
    )
    if irregular:
        reminders.append(
            {
                "type": "irregular",
                "level": "info",
                "title": "周期波动较大",
                "message": (
                    f"最近周期波动约 ±{variability:.1f} 天，预测已按趋势拟合，"
                    "并给出预测窗口。若长期不规律或伴随异常出血，建议咨询专业医生。"
                ),
            }
        )
    return reminders


def analyze_cycles(periods: list[dict], today: date | None = None) -> dict:
    today = today or date.today()

    items: list[dict] = []
    for period in periods:
        start = parse_date(period["start_date"])
        end = parse_date(period["end_date"]) if period.get("end_date") else None
        if end is not None and end < start:
            end = start
        items.append(
            {
                "id": period.get("id"),
                "start": start,
                "end": end,
                "flow": period.get("flow", "medium"),
                "symptoms": period.get("symptoms", "") or "",
                "notes": period.get("notes", "") or "",
            }
        )
    items.sort(key=lambda item: item["start"])

    cycle_lengths: list[int] = []
    for previous, current in zip(items, items[1:]):
        diff = (current["start"] - previous["start"]).days
        if MIN_CYCLE <= diff <= MAX_CYCLE:
            cycle_lengths.append(diff)
    recent = cycle_lengths[-MAX_CYCLES_USED:]

    if recent:
        average = mean(recent)
        median_value = median(recent)
        variability = pstdev(recent) if len(recent) > 1 else 0.0
    else:
        average = float(DEFAULT_CYCLE)
        median_value = float(DEFAULT_CYCLE)
        variability = 0.0
    average_cycle = _round(average)
    fit = _fit_cycles(recent)
    predicted_cycle = _round(fit["predicted_cycle"])
    predicted_cycle = max(MIN_CYCLE, min(MAX_CYCLE, predicted_cycle))
    irregular = bool(recent) and (
        (max(recent) - min(recent) >= IRREGULAR_RANGE) or variability >= 4.0
    )
    trend = _cycle_trend(recent)
    window_days = max(1, _round(variability)) if recent else 0
    fit_summary = {
        "predicted_cycle_length": predicted_cycle if recent else DEFAULT_CYCLE,
        "fit_method": fit["method"],
        "residual_std": round(fit["residual_std"], 1),
        "irregular": irregular,
        "cycle_trend": trend,
        "cycle_trend_label": CYCLE_TREND_LABELS[trend],
        "cycle_range_min": min(recent) if recent else None,
        "cycle_range_max": max(recent) if recent else None,
        "prediction_window_days": window_days,
    }

    period_lengths: list[int] = []
    for item in items:
        if item["end"] is not None:
            length = (item["end"] - item["start"]).days + 1
            if 1 <= length <= 15:
                period_lengths.append(length)
    average_period = (
        _round(mean(period_lengths[-MAX_CYCLES_USED:]))
        if period_lengths
        else DEFAULT_PERIOD
    )

    history: list[dict] = []
    for index, item in enumerate(items):
        cycle_length = None
        if index > 0:
            diff = (item["start"] - items[index - 1]["start"]).days
            if MIN_CYCLE <= diff <= MAX_CYCLE:
                cycle_length = diff
        history.append(
            {
                "id": item["id"],
                "start_date": item["start"].isoformat(),
                "end_date": item["end"].isoformat() if item["end"] else None,
                "flow": item["flow"],
                "symptoms": item["symptoms"],
                "notes": item["notes"],
                "period_length": (
                    (item["end"] - item["start"]).days + 1 if item["end"] else None
                ),
                "cycle_length": cycle_length,
            }
        )
    history.reverse()

    confidence, confidence_label = _confidence(len(recent), variability)

    if not items:
        return {
            "today": today.isoformat(),
            "has_data": False,
            "period_count": 0,
            "current": {
                "cycle_day": None,
                "cycle_progress": 0.0,
                "phase": "unknown",
                "phase_label": PHASE_INFO["unknown"]["label"],
                "phase_tip": PHASE_INFO["unknown"]["tip"],
                "days_until_next_period": None,
                "late_days": 0,
                "is_period_expected": False,
                "is_period_late": False,
            },
            "last_period": None,
            "current_cycle": None,
            "prediction": {
                "average_cycle_length": DEFAULT_CYCLE,
                "median_cycle_length": DEFAULT_CYCLE,
                "cycle_variability": 0.0,
                "average_period_length": DEFAULT_PERIOD,
                "cycles_used": 0,
                "confidence": "insufficient",
                "confidence_label": "数据不足",
                "next_period_start": None,
                "next_period_end": None,
                "prediction_window_start": None,
                "prediction_window_end": None,
                "ovulation_date": None,
                "fertile_window_start": None,
                "fertile_window_end": None,
                "upcoming_periods": [],
                **fit_summary,
            },
            "reminders": _build_reminders(
                today, None, None, None, None, None, None, False
            ),
            "history": history,
        }

    last = items[-1]
    last_start = last["start"]
    last_end = last["end"] or (last_start + timedelta(days=average_period - 1))
    if last_end < last_start:
        last_end = last_start

    next_start = last_start + timedelta(days=predicted_cycle)
    next_end = next_start + timedelta(days=average_period - 1)
    next_ovulation = next_start - timedelta(days=LUTEAL_DAYS)
    fertile_start = next_ovulation - timedelta(days=5)
    fertile_end = next_ovulation + timedelta(days=1)
    prediction_window_start = next_start - timedelta(days=window_days)
    prediction_window_end = next_start + timedelta(days=window_days)

    current_ovulation = last_start + timedelta(days=predicted_cycle - LUTEAL_DAYS)
    current_fertile_start = current_ovulation - timedelta(days=5)
    current_fertile_end = current_ovulation + timedelta(days=1)

    days_until = (next_start - today).days
    late_days = max(0, -days_until)
    cycle_day = max(1, (today - last_start).days + 1)

    if today < last_start:
        phase = "unknown"
    elif last_start <= today <= last_end:
        phase = "menstrual"
    elif current_fertile_start <= today <= current_fertile_end:
        phase = "ovulation"
    elif today < current_ovulation:
        phase = "follicular"
    else:
        phase = "luteal"

    cycle_progress = min(1.0, max(0.0, cycle_day / max(1, predicted_cycle)))

    upcoming_periods: list[dict] = []
    for index in range(1, FORECAST_CYCLES + 1):
        start = last_start + timedelta(days=predicted_cycle * index)
        end = start + timedelta(days=average_period - 1)
        ovulation = start - timedelta(days=LUTEAL_DAYS)
        upcoming_periods.append(
            {
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "ovulation_date": ovulation.isoformat(),
                "fertile_window_start": (ovulation - timedelta(days=5)).isoformat(),
                "fertile_window_end": (ovulation + timedelta(days=1)).isoformat(),
            }
        )

    return {
        "today": today.isoformat(),
        "has_data": True,
        "period_count": len(items),
        "current": {
            "cycle_day": cycle_day,
            "cycle_progress": round(cycle_progress, 4),
            "phase": phase,
            "phase_label": PHASE_INFO[phase]["label"],
            "phase_tip": PHASE_INFO[phase]["tip"],
            "days_until_next_period": days_until,
            "late_days": late_days,
            "is_period_expected": 0 <= days_until <= 7,
            "is_period_late": days_until < 0,
        },
        "last_period": {
            "id": last["id"],
            "start_date": last_start.isoformat(),
            "end_date": last["end"].isoformat() if last["end"] else None,
            "ongoing": last["end"] is None and today <= last_end,
        },
        "current_cycle": {
            "ovulation_date": current_ovulation.isoformat(),
            "fertile_window_start": current_fertile_start.isoformat(),
            "fertile_window_end": current_fertile_end.isoformat(),
        },
        "prediction": {
            "average_cycle_length": average_cycle,
            "median_cycle_length": _round(median_value),
            "cycle_variability": round(variability, 1),
            "average_period_length": average_period,
            "cycles_used": len(recent),
            "confidence": confidence,
            "confidence_label": confidence_label,
            "next_period_start": next_start.isoformat(),
            "next_period_end": next_end.isoformat(),
            "prediction_window_start": prediction_window_start.isoformat(),
            "prediction_window_end": prediction_window_end.isoformat(),
            "ovulation_date": next_ovulation.isoformat(),
            "fertile_window_start": fertile_start.isoformat(),
            "fertile_window_end": fertile_end.isoformat(),
            "upcoming_periods": upcoming_periods,
            **fit_summary,
        },
        "reminders": _build_reminders_with_irregular(
            today,
            last_start,
            last_end,
            next_start,
            current_fertile_start,
            current_fertile_end,
            days_until,
            irregular,
            variability,
        ),
        "history": history,
    }


def build_calendar(
    year: int,
    month: int,
    periods: list[dict],
    analysis: dict,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    first = date(year, month, 1)
    next_month = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
    day_count = (next_month - first).days

    flags: dict[str, dict[str, bool]] = {}

    def mark(value: date, key: str) -> None:
        if first <= value < next_month:
            flags.setdefault(value.isoformat(), {})[key] = True

    period_len = int(analysis["prediction"].get("average_period_length") or DEFAULT_PERIOD)

    for period in periods:
        start = parse_date(period["start_date"])
        end = parse_date(period["end_date"]) if period.get("end_date") else None
        if end is None:
            end = min(today, start + timedelta(days=period_len - 1))
        cursor = start
        while cursor <= end:
            mark(cursor, "actual")
            cursor += timedelta(days=1)

    current_cycle = analysis.get("current_cycle")
    if current_cycle:
        cursor = parse_date(current_cycle["fertile_window_start"])
        end = parse_date(current_cycle["fertile_window_end"])
        while cursor <= end:
            mark(cursor, "fertile")
            cursor += timedelta(days=1)
        mark(parse_date(current_cycle["ovulation_date"]), "ovulation")

    for upcoming in analysis["prediction"].get("upcoming_periods", []):
        cursor = parse_date(upcoming["start_date"])
        end = parse_date(upcoming["end_date"])
        while cursor <= end:
            mark(cursor, "predicted")
            cursor += timedelta(days=1)
        cursor = parse_date(upcoming["fertile_window_start"])
        end = parse_date(upcoming["fertile_window_end"])
        while cursor <= end:
            mark(cursor, "fertile")
            cursor += timedelta(days=1)
        mark(parse_date(upcoming["ovulation_date"]), "ovulation")

    days = []
    for offset in range(day_count):
        current = first + timedelta(days=offset)
        current_flags = flags.get(current.isoformat(), {})
        days.append(
            {
                "date": current.isoformat(),
                "day": current.day,
                "is_today": current == today,
                "actual": current_flags.get("actual", False),
                "predicted": current_flags.get("predicted", False),
                "fertile": current_flags.get("fertile", False),
                "ovulation": current_flags.get("ovulation", False),
            }
        )

    return {
        "year": year,
        "month": month,
        "first_weekday": first.weekday(),
        "days": days,
        "today": today.isoformat(),
    }
