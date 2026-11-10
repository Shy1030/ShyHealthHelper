from __future__ import annotations

from datetime import date

ACTIVITY_FACTORS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}


def _goal_plan(profile: dict, weight: float | None, tdee: int | None, today: date) -> dict:
    goal = profile.get("goal") or "maintain"
    target_weight = profile.get("target_weight_kg")
    plan: dict = {"has_target": False, "goal": goal}
    if not weight or not target_weight:
        return plan

    plan.update(
        {
            "has_target": True,
            "current_weight_kg": round(float(weight), 2),
            "target_weight_kg": round(float(target_weight), 2),
            "weight_diff_kg": round(float(weight) - float(target_weight), 2),
        }
    )
    target_date_value = profile.get("target_date")
    days_left = None
    if target_date_value:
        try:
            target_date = date.fromisoformat(str(target_date_value)[:10])
            days_left = (target_date - today).days
            plan["target_date"] = target_date.isoformat()
        except ValueError:
            days_left = None
    plan["days_left"] = days_left

    weight_diff = float(weight) - float(target_weight)  # 正数=需要减重
    if weight_diff > 0:
        plan["mode"] = "lose"
    elif weight_diff < 0:
        plan["mode"] = "gain"
    else:
        plan["mode"] = "maintain"

    if not days_left or days_left <= 0:
        plan["warning"] = "请设置一个未来的期望完成日期。"
        return plan

    weekly_change = weight_diff / days_left * 7
    daily_delta = weight_diff * 7700 / days_left
    plan.update(
        {
            "weekly_change_kg": round(weekly_change, 2),
            "daily_energy_delta": round(daily_delta),
            "daily_deficit": max(0, round(daily_delta)),
            "daily_surplus": max(0, -round(daily_delta)),
            "note": "按 1 kg 脂肪约 7700 千卡估算，实际会受水分、代谢和运动影响。",
        }
    )

    warning = ""
    if plan["mode"] == "lose":
        if weekly_change > 1.0:
            warning = "每周减重超过 1 kg，过于激进，建议延长期望时间或调高目标体重。"
        elif weekly_change > 0.75:
            warning = "每周减重超过 0.75 kg，偏快；建议控制在每周 0.25-0.75 kg。"
        elif weekly_change < 0.1:
            warning = "按当前期望时间，减重速度很慢；可以检查目标日期或目标体重。"
        if goal != "lose":
            warning = (warning + " ").strip() + "当前目标不是减脂，但目标体重低于当前体重。"
    elif plan["mode"] == "gain":
        if weekly_change < -0.75:
            warning = "每周增重超过 0.75 kg，脂肪增加可能偏多，建议放慢速度。"
        elif weekly_change > -0.1:
            warning = "按当前期望时间，增重速度很慢。"
        if goal != "gain":
            warning = (warning + " ").strip() + "当前目标不是增肌，但目标体重高于当前体重。"
    else:
        warning = "当前体重已达到目标。"

    plan["warning"] = warning.strip()
    if tdee:
        floor = 1500 if (profile.get("sex") or "female") == "male" else 1200
        projected_target = tdee - round(daily_delta)
        if projected_target < floor:
            plan["warning"] = (
                (plan["warning"] + " ").strip()
                + f" 按此计划每日热量会低于安全下限（{floor} 千卡），建议延长期望时间。"
            ).strip()
            plan["too_aggressive"] = True
    return plan


def compute_metrics(profile: dict, today: date | None = None) -> dict:
    today = today or date.today()
    height = profile.get("height_cm")
    weight = profile.get("weight_kg")
    birth_year = profile.get("birth_year")
    sex = profile.get("sex") or "female"
    activity = profile.get("activity_level") or "light"

    bmi = None
    if height and weight:
        bmi = round(weight / ((height / 100) ** 2), 1)

    age = today.year - birth_year if birth_year else None

    bmr = None
    if height and weight and age is not None:
        base = 10 * weight + 6.25 * height - 5 * age
        if sex == "male":
            bmr = base + 5
        elif sex == "female":
            bmr = base - 161
        else:
            bmr = base - 78
        bmr = round(bmr)

    factor = ACTIVITY_FACTORS.get(activity, 1.375)
    tdee = round(bmr * factor) if bmr else None

    return {
        "bmi": bmi,
        "age": age,
        "bmr": bmr,
        "tdee": tdee,
        "activity_factor": factor,
        "goal_plan": _goal_plan(profile, weight, tdee, today),
    }
