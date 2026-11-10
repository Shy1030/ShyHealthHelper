from __future__ import annotations

import asyncio
import base64
import json
import re
from datetime import date
from typing import Any

import httpx

from .config import settings
from .exercise_estimation import (
    as_bool,
    enrich_record,
    records_from_description,
    summarize_records,
)


class AIError(Exception):
    """DeepSeek 调用失败时抛出，路由层会转换成友好的 HTTP 错误。"""


VISION_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
}

DIET_SYSTEM_PROMPT = """你是一位严谨的注册营养师，擅长中餐营养估算与食物照片识别。
请估算用户这一餐的营养摄入，并给出具体、温和、可执行的建议。

硬性要求：
1. 如果用户提供了照片，请先识别照片中的食物种类与大致份量，再结合文字描述估算；
   文字描述与照片冲突时，以文字描述为准。
2. 只输出一个 JSON 对象，不要输出 Markdown 代码块或任何解释文字。
3. 数值为一人份估算值，热量单位千卡(kcal)，蛋白质/脂肪/碳水/膳食纤维/糖单位克(g)，钠单位毫克(mg)。
4. 不确定的食材按常见做法与常规份量估算，不要编造精确到小数点的虚假数据。
5. advice 是 2-5 条针对这一餐的建议；tips 是 2-4 条当天可执行的饮食小贴士。
6. 必须提醒这是估算值，不构成医疗建议。

JSON 结构：
{
  "foods": [
    {"name": "食物名称", "portion": "份量描述", "calories": 0, "protein": 0, "fat": 0, "carbs": 0}
  ],
  "totals": {"calories": 0, "protein": 0, "fat": 0, "carbs": 0, "fiber": 0, "sugar": 0, "sodium": 0},
  "score": 70,
  "advice": ["..."],
  "tips": ["..."],
  "confidence": "low|medium|high",
  "note": "基于文字描述的估算，仅供参考"
}
"""

EXERCISE_SYSTEM_PROMPT = """你是一位运动康复师与女性健康教练。请根据用户的身体数据和月经周期阶段，
制定安全、个性、可执行的一周运动计划。

硬性要求：
1. 只输出一个 JSON 对象，不要输出 Markdown 代码块或任何解释文字。
2. 经期（menstrual）避免高强度、倒立、腹部高压和剧烈跳跃，以恢复性运动为主。
3. 卵泡期（follicular）可逐步增加力量与有氧强度；排卵期（ovulation）可中高强度；
   黄体期（luteal）以中低强度为主并注意恢复；unknown 时按均衡计划。
4. 若用户填写了伤病，必须给出替代动作与风险提示。
5. 如果提供了最近运动记录，请沿用用户已有的运动习惯，避免突然大幅加量。
6. 建议不构成医疗诊断，身体不适时停止运动并咨询医生。
7. 必须遵守用户填写的训练偏好、场地、器械、每周训练天数和时长；
   如果每周训练天数少于 7 天，其余天安排休息或恢复活动。

JSON 结构：
{
  "summary": "一句话总结本周训练重点",
  "weekly_plan": [
    {"day": "周一", "focus": "训练主题", "workout": "具体动作与组数", "duration_min": 30, "intensity": "low|moderate|high", "notes": "注意事项"}
  ],
  "nutrition_tips": ["..."],
  "cautions": ["..."],
  "phase_note": "结合当前周期的说明"
}
weekly_plan 必须包含周一到周日 7 天，休息日也要给出恢复建议。
"""

EXERCISE_SCREENSHOT_PROMPT = """你是一位运动数据分析助手。用户会上传运动 App 或智能手环的截图，
请识别截图中的运动记录并整理成结构化数据。

硬性要求：
1. 只输出一个 JSON 对象，不要输出 Markdown 代码块或任何解释文字。
2. 一张截图里可能有多条运动记录，请逐条提取；没有的字段填 null，不要编造。
3. 日期尽量使用截图中的日期，格式 YYYY-MM-DD；无法确定时使用今天。
4. duration_min 单位分钟，calories 单位千卡，distance_km 单位公里，steps 为步数，
   avg_heart_rate 单位次/分，start_time 格式 HH:MM。
5. 识别运动类型时使用常见中文名称，例如 跑步、骑行、快走、游泳、力量训练、瑜伽、跳绳。
6. confidence 表示识别把握：low / medium / high。
7. 如果截图里有运动类型和时长、但没有热量：请根据用户体重和运动类型，用 MET 公式估算热量，
   并设置 calories_estimated=true、calorie_basis 说明估算依据，不要留空。
8. 如果截图中没有明确时长，但能推断出合理时长，请填写 duration_min 并设置
   duration_estimated=true。
9. 如果截图中已有热量数据，calories_estimated=false，calorie_basis 写“截图中的热量数据”。

JSON 结构：
{
  "records": [
    {
      "date": "2026-11-07",
      "start_time": "07:30",
      "activity": "跑步",
      "duration_min": 32,
      "calories": 280,
      "calories_estimated": false,
      "duration_estimated": false,
      "calorie_basis": "截图中的热量数据",
      "distance_km": 4.2,
      "steps": 5200,
      "avg_heart_rate": 145,
      "intensity": "moderate",
      "notes": "截图 OCR 识别"
    }
  ],
  "summary": "本次截图共识别 1 条运动记录",
  "confidence": "medium",
  "note": "数值来自截图识别，可能与原始记录存在偏差"
}
"""

EXERCISE_DESCRIBE_PROMPT = """你是一位运动数据分析助手。用户会用自然语言描述自己今天的运动，
请把描述整理成结构化的运动记录，并在缺少热量数据时按 MET 估算。

硬性要求：
1. 只输出一个 JSON 对象，不要输出 Markdown 代码块或任何解释文字。
2. 一条描述可能包含多项运动，请逐条提取；不要编造用户没有提到的运动。
3. 日期使用用户提供的日期，格式 YYYY-MM-DD。
4. duration_min 单位分钟；如果用户没有说时长，按常见运动习惯推断，并设置
   duration_estimated=true。
5. calories 单位千卡；如果用户没有提供热量，根据用户体重、运动类型和时长用 MET 估算，
   设置 calories_estimated=true，并在 calorie_basis 写明“MET、体重、时长”等依据。
6. intensity 取值 low / moderate / high；无法判断时用 moderate。
7. confidence 表示解析把握：low / medium / high。
8. 注意从“快走 30 分钟、跑了 5 公里、1 小时力量训练”等表述中解析数值。

JSON 结构：
{
  "records": [
    {
      "date": "2026-11-07",
      "activity": "快走",
      "duration_min": 30,
      "duration_estimated": false,
      "calories": 120,
      "calories_estimated": true,
      "calorie_basis": "快走 MET 4.3 · 体重 55kg · 30分钟",
      "distance_km": null,
      "steps": null,
      "intensity": "low",
      "notes": "用户文字描述"
    }
  ],
  "summary": "从描述中整理出 1 条运动记录",
  "confidence": "medium",
  "note": "热量为估算值，仅供参考"
}
"""

MEAL_RECOMMEND_SYSTEM_PROMPT = """你是一位注册营养师与运动教练。用户会提供体重、目标、今日已摄入热量和营养物质、
每日推荐热量、剩余热量、已记录餐次以及今日运动。请直接基于这些数据推荐下一餐和今天还可做的运动。

硬性要求：
1. 只输出一个 JSON 对象，不要输出 Markdown 代码块或任何解释文字。
2. 推荐必须基于“已摄入 / 每日推荐 / 剩余 / 蛋白质缺口”和已记录餐次，不能忽略今日运动消耗。
3. 如果今日热量已超出目标，下一餐要清淡、少油少糖，并控制份量。
4. 优先补充蛋白质和蔬菜，主食适量；具体到菜名、份量和大致热量。
5. 运动建议要结合目标（减脂/保持/增肌）和今天已经完成的运动量，避免过量。
6. 数值为估算值，不构成医疗建议；身体不适时停止运动并咨询医生。

JSON 结构：
{
  "summary": "一句话说明下一餐重点",
  "target_calories": 500,
  "dishes": [
    {"name": "清蒸鲈鱼", "portion": "150g", "calories": 220, "protein": 30, "reason": "补充优质蛋白"}
  ],
  "meal_tips": ["先吃蔬菜和蛋白质，再吃主食"],
  "exercise": [
    {"name": "快走", "duration_min": 30, "intensity": "low|moderate|high", "reason": "帮助餐后血糖稳定"}
  ],
  "exercise_note": "结合今天已经完成的运动，说明强度安排",
  "note": "估算值仅供参考"
}
"""

CHAT_SYSTEM_PROMPT = """你是 ShyHealthHelper 的营养与运动助手，只回答营养、饮食、运动、体重管理和热量平衡相关问题。
回答时优先结合用户提供的体重、目标、今日摄入、运动消耗、热量缺口和月经周期阶段。
要求：
1. 简洁、具体、可执行，尽量给出数字、食物例子或运动时长。
2. 不做医疗诊断；涉及疾病、药物、严重不适或月经长期紊乱时，建议咨询医生。
3. 不确定的信息要说明，不要编造精确数据。
4. 如果用户只是闲聊或询问无关内容，礼貌地把话题引导回营养与运动。
5. 用中文回答，控制在 300 字以内，除非用户要求展开。
"""

MEAL_LABELS = {
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
    "snack": "加餐",
}


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise AIError("AI 返回内容不是有效 JSON，请重试")
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AIError("AI 返回内容解析失败，请重试") from exc
    if not isinstance(parsed, dict):
        raise AIError("AI 返回内容格式不正确，请重试")
    return parsed


def _user_content(
    text: str, image: tuple[bytes, str] | None = None
) -> str | list[dict]:
    if not image or image[1] not in VISION_MIME_TYPES:
        return text
    data, mime = image
    encoded = base64.b64encode(data).decode("ascii")
    return [
        {"type": "text", "text": text},
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime};base64,{encoded}",
                "detail": "auto",
            },
        },
    ]


async def _chat_completion(
    messages: list[dict],
    temperature: float = 0.3,
    json_mode: bool = False,
    max_tokens: int = 3000,
    model: str | None = None,
) -> str:
    if settings.mock_mode:
        raise AIError("当前为本地模式，暂未调用 DeepSeek")

    payload = {
        "model": model or settings.deepseek_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    url = f"{settings.deepseek_base_url}/chat/completions"

    last_error = "未知错误"
    async with httpx.AsyncClient(timeout=settings.timeout) as client:
        for attempt in range(3):
            try:
                response = await client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException:
                last_error = "请求超时"
                await asyncio.sleep(1.0 * (attempt + 1))
                continue
            except httpx.HTTPError as exc:
                last_error = f"网络错误：{exc}"
                await asyncio.sleep(1.0 * (attempt + 1))
                continue

            if response.status_code == 401:
                raise AIError("DeepSeek API Key 无效或已过期，请检查 DEEPSEEK_API_KEY")
            if response.status_code == 402:
                raise AIError("DeepSeek 账户余额不足，请充值后重试")
            if response.status_code == 429:
                last_error = "请求过于频繁，已限流"
                await asyncio.sleep(2.0 * (attempt + 1))
                continue
            if response.status_code >= 500:
                last_error = f"DeepSeek 服务异常 ({response.status_code})"
                await asyncio.sleep(1.2 * (attempt + 1))
                continue
            if response.status_code != 200:
                detail = response.text[:200]
                raise AIError(f"DeepSeek 调用失败 ({response.status_code})：{detail}")

            try:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError):
                last_error = "DeepSeek 返回结构异常"
                await asyncio.sleep(0.8 * (attempt + 1))
                continue

    raise AIError(f"DeepSeek 调用失败：{last_error}")


async def chat_json(
    system: str,
    user: str,
    image: tuple[bytes, str] | None = None,
    temperature: float = 0.3,
) -> dict:
    use_vision = bool(image and image[1] in VISION_MIME_TYPES)
    model = (
        settings.deepseek_vision_model if use_vision else settings.deepseek_model
    )
    content = await _chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": _user_content(user, image)},
        ],
        temperature=temperature,
        json_mode=True,
        max_tokens=3000,
        model=model,
    )
    return _extract_json(content)


def _number(value: Any, default: float = 0.0, maximum: float = 100000.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if result != result or result < 0:
        return default
    return round(min(result, maximum), 1)


def _text_list(value: Any, limit: int = 6) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip()[:200])
        if len(result) >= limit:
            break
    return result


def _normalize_diet(data: dict, description: str) -> dict:
    foods = []
    raw_foods = data.get("foods")
    if isinstance(raw_foods, list):
        for item in raw_foods[:12]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            foods.append(
                {
                    "name": name[:40],
                    "portion": str(item.get("portion") or "约一份")[:40],
                    "calories": _number(item.get("calories"), 0, 5000),
                    "protein": _number(item.get("protein"), 0, 500),
                    "fat": _number(item.get("fat"), 0, 500),
                    "carbs": _number(item.get("carbs"), 0, 500),
                }
            )

    if not foods:
        foods = [
            {
                "name": (description[:24] or "本餐"),
                "portion": "一人份",
                "calories": 0,
                "protein": 0,
                "fat": 0,
                "carbs": 0,
            }
        ]

    totals = data.get("totals") if isinstance(data.get("totals"), dict) else {}
    calories = _number(totals.get("calories"), 0, 8000)
    protein = _number(totals.get("protein"), 0, 1000)
    fat = _number(totals.get("fat"), 0, 1000)
    carbs = _number(totals.get("carbs"), 0, 1500)
    if calories == 0:
        calories = _number(sum(food["calories"] for food in foods), 0, 8000)
    if protein == 0:
        protein = _number(sum(food["protein"] for food in foods), 0, 1000)
    if fat == 0:
        fat = _number(sum(food["fat"] for food in foods), 0, 1000)
    if carbs == 0:
        carbs = _number(sum(food["carbs"] for food in foods), 0, 1500)

    score = int(_number(data.get("score"), 70, 100))
    confidence = str(data.get("confidence") or "medium").lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "medium"

    advice = _text_list(data.get("advice"), 5) or ["记录得不错，继续保持饮食多样性。"]
    tips = _text_list(data.get("tips"), 4) or ["多喝水，搭配蔬菜和优质蛋白。"]
    note = str(
        data.get("note")
        or "营养数据为基于文字描述的估算，仅供参考，不构成医疗建议。"
    )[:300]

    return {
        "foods": foods,
        "totals": {
            "calories": calories,
            "protein": protein,
            "fat": fat,
            "carbs": carbs,
            "fiber": _number(totals.get("fiber"), 0, 300),
            "sugar": _number(totals.get("sugar"), 0, 500),
            "sodium": _number(totals.get("sodium"), 0, 20000),
        },
        "score": score,
        "advice": advice,
        "tips": tips,
        "confidence": confidence,
        "note": note,
    }


def _mock_diet(
    description: str, meal_type: str, profile: dict, has_image: bool = False
) -> dict:
    base = {"breakfast": 430, "lunch": 660, "dinner": 560, "snack": 230}.get(
        meal_type, 520
    )
    text = description or ""
    if any(word in text for word in ("炸", "奶茶", "蛋糕", "烧烤", "火锅")):
        base += 220
    if any(word in text for word in ("沙拉", "蔬菜", "清蒸", "水煮")):
        base -= 80
    base = max(120, base)

    pieces = [
        piece.strip()
        for piece in re.split(r"[，,、;；/]|和|加", text)
        if piece.strip()
    ][:4]
    if not pieces:
        pieces = [text[:20] or "本餐"]

    per = base / len(pieces)
    foods = []
    for piece in pieces:
        foods.append(
            {
                "name": piece[:24],
                "portion": "约一人份",
                "calories": round(per, 1),
                "protein": round(per * 0.20 / 4, 1),
                "fat": round(per * 0.30 / 9, 1),
                "carbs": round(per * 0.50 / 4, 1),
            }
        )

    protein = round(base * 0.20 / 4, 1)
    fat = round(base * 0.30 / 9, 1)
    carbs = round(base * 0.50 / 4, 1)
    bmi = profile.get("bmi")
    goal = profile.get("goal")

    advice = [
        f"这一餐约 {int(base)} 千卡，蛋白质、脂肪、碳水比例约为 20% / 30% / 50%。",
        "先吃蔬菜和蛋白质，再吃主食，有助于稳定餐后血糖。" ,
    ]
    if goal == "lose":
        advice.append("减脂期建议控制精制主食和含糖饮料，晚餐七分饱即可。")
    elif goal == "gain":
        advice.append("增肌期可适当增加优质蛋白与主食份量，训练后及时补充。")
    if bmi and bmi >= 24:
        advice.append("当前 BMI 偏高，建议减少油炸食品，增加蔬菜与日常步行。")
    elif bmi and bmi < 18.5:
        advice.append("当前 BMI 偏低，建议增加坚果、奶类和优质蛋白的摄入。")

    tips = [
        "每天喝够 1500-2000 毫升水。",
        "保证一拳蔬菜、一掌蛋白质、一拳主食的搭配。",
        "营养数据为估算值，仅供参考。",
    ]

    return {
        "foods": foods,
        "totals": {
            "calories": round(base, 1),
            "protein": protein,
            "fat": fat,
            "carbs": carbs,
            "fiber": round(base * 0.012, 1),
            "sugar": round(base * 0.03, 1),
            "sodium": round(base * 1.8, 1),
        },
        "score": 72,
        "advice": advice,
        "tips": tips,
        "confidence": "low",
        "note": "营养数据为估算值，仅供参考，不构成医疗建议。",
    }


async def analyze_diet(
    description: str,
    meal_type: str,
    profile: dict,
    image: tuple[bytes, str] | None = None,
) -> tuple[dict, str]:
    has_image = bool(image and image[1] in VISION_MIME_TYPES)
    if settings.mock_mode:
        return _mock_diet(description, meal_type, profile, has_image), "mock"

    meal_label = MEAL_LABELS.get(meal_type, meal_type or "用餐")
    user_prompt = json.dumps(
        {
            "餐次": meal_label,
            "文字描述": description or "（未填写，请主要根据照片识别）",
            "是否附照片": has_image,
            "用户资料": {
                "性别": profile.get("sex"),
                "年龄": profile.get("age"),
                "身高cm": profile.get("height_cm"),
                "体重kg": profile.get("weight_kg"),
                "BMI": profile.get("bmi"),
                "目标": profile.get("goal"),
            },
            "说明": (
                "已附照片：请优先识别照片中的食物种类与份量，再结合文字描述估算。"
                if has_image
                else "未附照片：请仅根据文字描述估算，并说明不确定性。"
            ),
        },
        ensure_ascii=False,
    )
    data = await chat_json(
        DIET_SYSTEM_PROMPT, user_prompt, image=image, temperature=0.2
    )
    return _normalize_diet(data, description), "deepseek"


def _mock_exercise(profile: dict, phase: str) -> dict:
    phase = phase if phase in {"menstrual", "follicular", "ovulation", "luteal"} else "unknown"
    plans = {
        "menstrual": [
            ("恢复", "舒缓散步 + 全身拉伸", 25, "low"),
            ("恢复", "经期瑜伽（避免倒立）", 20, "low"),
            ("轻有氧", "快走，保持能正常说话", 30, "low"),
            ("休息", "热敷、腹式呼吸与充足睡眠", 15, "low"),
            ("轻力量", "自重深蹲、臀桥（低强度）", 25, "low"),
            ("恢复", "散步 + 泡沫轴放松", 20, "low"),
            ("休息", "自由活动，注意补铁与补水", 15, "low"),
        ],
        "follicular": [
            ("力量", "下肢力量：深蹲、箭步蹲、臀桥 3 组", 45, "moderate"),
            ("有氧", "慢跑或骑行 30 分钟", 35, "moderate"),
            ("力量", "上肢推拉：俯卧撑、划船 3 组", 45, "moderate"),
            ("恢复", "瑜伽或拉伸 20 分钟", 20, "low"),
            ("力量", "核心与臀腿循环训练 4 轮", 40, "high"),
            ("有氧", "间歇快走或跳绳 20 分钟", 30, "moderate"),
            ("休息", "散步与规律作息", 20, "low"),
        ],
        "ovulation": [
            ("高强度", "HIIT 20 分钟 + 热身放松", 30, "high"),
            ("力量", "全身复合动作 4 组", 50, "high"),
            ("有氧", "跑步或游泳 35 分钟", 40, "moderate"),
            ("恢复", "拉伸与呼吸练习", 20, "low"),
            ("力量", "臀腿力量训练 4 组", 45, "high"),
            ("有氧", "舞蹈或球类运动 40 分钟", 45, "moderate"),
            ("休息", "轻松散步，注意补水", 20, "low"),
        ],
        "luteal": [
            ("中低强度", "快走 30 分钟", 30, "low"),
            ("力量", "轻重量全身训练 3 组", 35, "moderate"),
            ("恢复", "普拉提或瑜伽 25 分钟", 25, "low"),
            ("有氧", "椭圆机或骑行 30 分钟", 30, "moderate"),
            ("力量", "臀腿低强度训练 3 组", 35, "moderate"),
            ("恢复", "拉伸 + 泡沫轴放松", 20, "low"),
            ("休息", "散步与早睡，控制盐分", 20, "low"),
        ],
        "unknown": [
            ("均衡", "快走 30 分钟", 30, "moderate"),
            ("力量", "自重全身训练 3 组", 35, "moderate"),
            ("恢复", "瑜伽或拉伸", 20, "low"),
            ("有氧", "骑行或慢跑 30 分钟", 30, "moderate"),
            ("力量", "核心训练 3 组", 30, "moderate"),
            ("有氧", "周末户外活动 45 分钟", 45, "moderate"),
            ("休息", "散步与规律作息", 20, "low"),
        ],
    }
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekly_plan = [
        {
            "day": weekdays[index],
            "focus": focus,
            "workout": workout,
            "duration_min": duration,
            "intensity": intensity,
            "notes": "如出现疼痛、头晕或异常出血，请立即停止运动。",
        }
        for index, (focus, workout, duration, intensity) in enumerate(plans[phase])
    ]
    phase_labels = {
        "menstrual": "经期",
        "follicular": "卵泡期",
        "ovulation": "排卵期",
        "luteal": "黄体期",
        "unknown": "周期未知",
    }
    cautions = [
        "运动前热身 5-10 分钟，运动后拉伸放松。",
        "如出现明显疲劳、疼痛或异常出血，请停止运动并咨询医生。",
    ]
    injuries = (profile.get("injuries") or "").strip()
    if injuries:
        cautions.insert(0, f"你填写了「{injuries}」，请避免相关动作或先咨询康复师。")

    return {
        "summary": (
            f"当前处于{phase_labels[phase]}，本周以"
            + ("恢复与轻活动为主。" if phase == "menstrual" else "循序渐进、规律训练为主。")
        ),
        "weekly_plan": weekly_plan,
        "nutrition_tips": [
            "训练日保证优质蛋白摄入，如鸡蛋、鱼虾、豆制品。",
            "经期注意补充含铁食物，如瘦肉、动物肝脏和深色蔬菜。",
            "根据身体感受和恢复情况调整训练量。",
        ],
        "cautions": cautions,
        "phase_note": f"当前周期阶段：{phase_labels[phase]}。请根据身体感受随时调整强度。",
    }


async def build_exercise_plan(
    profile: dict,
    metrics: dict,
    phase: str,
    cycle_day: int | None,
    activity_summary: dict | None = None,
    preferences: str = "",
) -> tuple[dict, str]:
    preferences = (preferences or "").strip()[:1000]
    if settings.mock_mode:
        plan = _mock_exercise(profile, phase)
        if preferences:
            plan["preferences"] = preferences
            plan["phase_note"] = (
                str(plan.get("phase_note") or "")
                + f" 已参考你的条件：{preferences[:200]}"
            ).strip()
            plan["summary"] = (
                str(plan.get("summary") or "")
                + "（Mock 模式未真正定制训练内容）"
            )
        return plan, "mock"

    payload = {
        "训练偏好与条件": preferences or "无",
        "用户资料": {
            "性别": profile.get("sex"),
            "年龄": profile.get("age"),
            "身高cm": profile.get("height_cm"),
            "体重kg": profile.get("weight_kg"),
            "BMI": metrics.get("bmi"),
            "基础代谢BMR": metrics.get("bmr"),
            "每日总消耗TDEE": metrics.get("tdee"),
            "日常活动水平": profile.get("activity_level"),
            "目标": profile.get("goal"),
            "伤病或限制": profile.get("injuries") or "无",
        },
        "月经周期": {"阶段": phase, "周期第几天": cycle_day},
    }
    if activity_summary and activity_summary.get("sessions"):
        payload["最近运动记录"] = {
            "统计天数": activity_summary.get("days"),
            "运动次数": activity_summary.get("sessions"),
            "运动天数": activity_summary.get("active_days"),
            "总时长分钟": activity_summary.get("total_duration_min"),
            "主要项目": activity_summary.get("by_activity"),
            "说明": "请结合用户已有运动习惯调整强度，避免突然大幅加量。",
        }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    data = await chat_json(EXERCISE_SYSTEM_PROMPT, user_prompt, temperature=0.4)

    plan = data.get("weekly_plan")
    weekly_plan = []
    if isinstance(plan, list):
        for index, item in enumerate(plan[:7]):
            if not isinstance(item, dict):
                continue
            intensity = str(item.get("intensity") or "moderate").lower()
            if intensity not in {"low", "moderate", "high"}:
                intensity = "moderate"
            weekly_plan.append(
                {
                    "day": str(item.get("day") or f"第{index + 1}天")[:10],
                    "focus": str(item.get("focus") or "训练")[:30],
                    "workout": str(item.get("workout") or "按身体状态活动")[:300],
                    "duration_min": int(_number(item.get("duration_min"), 30, 240)),
                    "intensity": intensity,
                    "notes": str(item.get("notes") or "")[:200],
                }
            )
    if not weekly_plan:
        weekly_plan = _mock_exercise(profile, phase)["weekly_plan"]

    return {
        "summary": str(data.get("summary") or "本周保持规律运动与充分恢复。")[:300],
        "weekly_plan": weekly_plan,
        "nutrition_tips": _text_list(data.get("nutrition_tips"), 5)
        or ["训练日注意补充蛋白质与水分。"],
        "cautions": _text_list(data.get("cautions"), 5)
        or ["如身体不适请停止运动并咨询医生。"],
        "phase_note": str(data.get("phase_note") or "")[:300],
        "preferences": preferences,
    }, "deepseek"


def _parse_log_date(value: Any, default: date | None = None) -> str:
    text = str(value or "").strip()
    match = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if match:
        try:
            return date(
                int(match.group(1)), int(match.group(2)), int(match.group(3))
            ).isoformat()
        except ValueError:
            pass
    return (default or date.today()).isoformat()


def _parse_log_time(value: Any) -> str | None:
    text = str(value or "").strip()
    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return f"{hour:02d}:{minute:02d}"
    return None


def _normalize_exercise_analysis(
    data: dict,
    note: str = "",
    profile: dict | None = None,
    default_date: date | None = None,
) -> dict:
    raw_records = data.get("records")
    if not isinstance(raw_records, list):
        raw_records = [data] if isinstance(data, dict) and data.get("activity") else []

    weight = (profile or {}).get("weight_kg")
    records: list[dict] = []
    for item in raw_records[:10]:
        if not isinstance(item, dict):
            continue
        activity = str(item.get("activity") or item.get("type") or "").strip()
        if not activity:
            activity = "运动"
        duration = _number(item.get("duration_min"), 0, 1440)
        calories = _number(item.get("calories"), 0, 20000)
        distance = _number(item.get("distance_km"), 0, 2000)
        steps = _number(item.get("steps"), 0, 300000)
        heart_rate = _number(item.get("avg_heart_rate"), 0, 250)
        record = {
            "log_date": _parse_log_date(item.get("date"), default=default_date),
            "start_time": _parse_log_time(item.get("start_time")),
            "activity": activity[:40],
            "duration_min": round(duration, 1) if duration else None,
            "calories": round(calories, 1) if calories else None,
            "distance_km": round(distance, 2) if distance else None,
            "steps": int(steps) if steps else None,
            "avg_heart_rate": int(heart_rate) if heart_rate else None,
            "notes": str(item.get("notes") or note or "")[:200],
            "intensity": str(item.get("intensity") or "").lower()[:10] or None,
            "calories_estimated": as_bool(item.get("calories_estimated")),
            "duration_estimated": as_bool(item.get("duration_estimated")),
            "calorie_basis": str(item.get("calorie_basis") or "")[:300],
        }
        records.append(enrich_record(record, weight))

    confidence = str(data.get("confidence") or "medium").lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "medium"

    stats = summarize_records(records)
    note_text = str(
        data.get("note")
        or "运动数据来自截图识别，可能与原始记录存在偏差，仅供参考。"
    )[:300]
    if stats["estimated_sessions"]:
        note_text = (
            note_text.rstrip("。")
            + "。缺少热量的记录已按体重与运动类型估算，仅供参考。"
        )[:300]

    return {
        "records": records,
        "summary": str(data.get("summary") or "已识别截图中的运动记录")[:200],
        "confidence": confidence,
        "note": note_text,
        "estimated_sessions": stats["estimated_sessions"],
        "estimated_calories": stats["estimated_calories"],
    }


def _mock_exercise_screenshot(note: str) -> dict:
    return {
        "records": [
            {
                "log_date": date.today().isoformat(),
                "start_time": "07:30",
                "activity": "快走",
                "duration_min": 30.0,
                "calories": None,
                "distance_km": 2.5,
                "steps": 3500,
                "avg_heart_rate": 110,
                "intensity": "low",
                "notes": note or "运动记录",
            }
        ],
        "summary": "已整理一条运动记录（Mock）",
        "confidence": "low",
        "note": "Mock 模式：热量由本地估算。",
    }


async def analyze_exercise_screenshot(
    note: str,
    image: tuple[bytes, str] | None,
    profile: dict | None = None,
) -> tuple[dict, str]:
    if settings.mock_mode:
        return (
            _normalize_exercise_analysis(
                _mock_exercise_screenshot(note), note, profile
            ),
            "mock",
        )

    weight = (profile or {}).get("weight_kg")
    user_prompt = json.dumps(
        {
            "补充说明": note or "（无）",
            "用户体重kg": weight,
            "说明": "请识别截图中的全部运动记录并按要求输出 JSON；缺少热量时按体重估算。",
        },
        ensure_ascii=False,
    )
    data = await chat_json(
        EXERCISE_SCREENSHOT_PROMPT, user_prompt, image=image, temperature=0.2
    )
    return _normalize_exercise_analysis(data, note, profile), "deepseek"


async def analyze_exercise_description(
    description: str,
    log_date: date | None = None,
    profile: dict | None = None,
) -> tuple[dict, str]:
    target_date = log_date or date.today()
    weight = (profile or {}).get("weight_kg")

    if settings.mock_mode:
        records = records_from_description(description, target_date, weight)
        stats = summarize_records(records)
        return (
            {
                "records": records,
                "summary": f"从描述中整理出 {len(records)} 条运动记录（Mock）",
                "confidence": "low",
                "note": "Mock 模式：已按运动类型、时长与体重用 MET 估算热量。",
                "estimated_sessions": stats["estimated_sessions"],
                "estimated_calories": stats["estimated_calories"],
            },
            "mock",
        )

    user_prompt = json.dumps(
        {
            "日期": target_date.isoformat(),
            "运动描述": description,
            "用户资料": {
                "体重kg": weight,
                "性别": (profile or {}).get("sex"),
                "年龄": (profile or {}).get("age"),
            },
            "说明": "请解析描述中的全部运动并按要求输出 JSON。",
        },
        ensure_ascii=False,
    )
    data = await chat_json(
        EXERCISE_DESCRIBE_PROMPT, user_prompt, temperature=0.2
    )
    analysis = _normalize_exercise_analysis(
        data, description, profile, default_date=target_date
    )
    if not analysis["records"]:
        records = records_from_description(description, target_date, weight)
        stats = summarize_records(records)
        analysis = {
            "records": records,
            "summary": f"从描述中整理出 {len(records)} 条运动记录",
            "confidence": "low",
            "note": "AI 未返回可用记录，已使用本地规则解析并估算热量。",
            "estimated_sessions": stats["estimated_sessions"],
            "estimated_calories": stats["estimated_calories"],
        }
    return analysis, "deepseek"


def _dish_list(value: Any, limit: int = 8) -> list[dict]:
    if not isinstance(value, list):
        return []
    dishes = []
    for item in value[:limit]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        dishes.append(
            {
                "name": name[:40],
                "portion": str(item.get("portion") or "一份")[:40],
                "calories": int(_number(item.get("calories"), 0, 3000)),
                "protein": _number(item.get("protein"), 0, 300),
                "reason": str(item.get("reason") or "")[:100],
            }
        )
    return dishes


def _exercise_list(value: Any, limit: int = 6) -> list[dict]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value[:limit]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        intensity = str(item.get("intensity") or "moderate").lower()
        if intensity not in {"low", "moderate", "high"}:
            intensity = "moderate"
        items.append(
            {
                "name": name[:40],
                "duration_min": int(_number(item.get("duration_min"), 20, 180)),
                "intensity": intensity,
                "reason": str(item.get("reason") or "")[:100],
            }
        )
    return items


def _normalize_meal_recommendation(data: dict, meal_type: str) -> dict:
    dishes = _dish_list(data.get("dishes"))
    exercise = _exercise_list(data.get("exercise"))
    target_calories = int(_number(data.get("target_calories"), 0, 3000))
    if not target_calories:
        target_calories = int(sum(dish["calories"] for dish in dishes))

    return {
        "meal_type": meal_type,
        "meal_label": MEAL_LABELS.get(meal_type, "用餐"),
        "summary": str(data.get("summary") or "结合今日摄入安排下一餐。")[:300],
        "target_calories": target_calories,
        "dishes": dishes,
        "meal_tips": _text_list(data.get("meal_tips"), 5)
        or ["先吃蔬菜和蛋白质，再吃主食。"],
        "exercise": exercise,
        "exercise_note": str(data.get("exercise_note") or "")[:300],
        "note": str(
            data.get("note") or "热量与运动建议为估算值，仅供参考，不构成医疗建议。"
        )[:300],
    }


def _mock_meal_recommendation(
    daily: dict,
    profile: dict,
    meal_type: str,
) -> dict:
    remaining = int((daily.get("remaining") or {}).get("calories") or 500)
    goal = profile.get("goal") or "maintain"
    today_exercise = (daily.get("exercise") or {}).get("today") or {}
    today_minutes = float(today_exercise.get("duration_min") or 0)
    meal_label = MEAL_LABELS.get(meal_type, "用餐")
    meal_target = max(250, min(700, remaining)) if remaining > 0 else 300

    if remaining <= 200:
        dishes = [
            {
                "name": "豆腐菌菇蔬菜汤",
                "portion": "一大碗",
                "calories": 180,
                "protein": 14,
                "reason": "热量较低，补充蛋白质和蔬菜",
            },
            {
                "name": "小份杂粮饭",
                "portion": "80g",
                "calories": 100,
                "protein": 3,
                "reason": "提供少量主食，避免夜间饥饿",
            },
        ]
        summary = f"今日热量额度不多，{meal_label}建议清淡少量，控制在约 280 千卡。"
    elif meal_type == "breakfast":
        dishes = [
            {"name": "燕麦牛奶", "portion": "250ml", "calories": 300, "protein": 18, "reason": "提供缓释碳水和蛋白质"},
            {"name": "水煮蛋", "portion": "1 个", "calories": 80, "protein": 7, "reason": "优质蛋白，增加饱腹感"},
            {"name": "蓝莓或苹果", "portion": "一小份", "calories": 60, "protein": 1, "reason": "补充维生素和膳食纤维"},
        ]
        summary = f"早餐建议约 {meal_target} 千卡，优先蛋白质和全谷物。"
    elif meal_type == "lunch":
        dishes = [
            {"name": "鸡胸肉藜麦饭", "portion": "一份", "calories": 480, "protein": 38, "reason": "蛋白质充足，主食适量"},
            {"name": "凉拌时蔬", "portion": "150g", "calories": 80, "protein": 4, "reason": "增加蔬菜和膳食纤维"},
        ]
        summary = f"午餐建议约 {meal_target} 千卡，保证蛋白质和蔬菜。"
    elif meal_type == "snack":
        dishes = [
            {"name": "无糖酸奶", "portion": "150g", "calories": 120, "protein": 8, "reason": "补充蛋白质，避免高糖零食"},
            {"name": "原味坚果", "portion": "一小把", "calories": 100, "protein": 3, "reason": "提供健康脂肪，控制份量"},
        ]
        summary = "加餐建议控制在 250 千卡以内，优先蛋白质和健康脂肪。"
    else:
        dishes = [
            {"name": "清蒸鲈鱼", "portion": "150g", "calories": 220, "protein": 30, "reason": "优质蛋白，少油烹饪"},
            {"name": "杂粮饭", "portion": "100g", "calories": 120, "protein": 4, "reason": "适量主食，稳定血糖"},
            {"name": "蒜蓉西兰花", "portion": "150g", "calories": 80, "protein": 5, "reason": "补充膳食纤维和维生素"},
        ]
        summary = f"晚餐建议约 {meal_target} 千卡，以蛋白质和蔬菜为主，主食适量。"

    if today_minutes >= 30:
        exercise = [
            {"name": "散步放松", "duration_min": 15, "intensity": "low", "reason": "今天运动量已够，帮助恢复"},
            {"name": "全身拉伸", "duration_min": 10, "intensity": "low", "reason": "缓解肌肉紧张"},
        ]
        exercise_note = f"今天已运动约 {int(today_minutes)} 分钟，不建议再增加高强度训练。"
    elif goal == "lose":
        exercise = [
            {"name": "快走或慢跑", "duration_min": 35, "intensity": "moderate", "reason": "制造温和热量缺口，帮助减脂"},
            {"name": "自重力量训练", "duration_min": 15, "intensity": "moderate", "reason": "保留肌肉量，避免代谢下降"},
        ]
        exercise_note = f"今日还可摄入 {max(0, remaining)} 千卡，配合 35 分钟有氧更有利于减脂。"
    elif goal == "gain":
        exercise = [
            {"name": "力量训练", "duration_min": 25, "intensity": "moderate", "reason": "增肌期优先保证力量刺激"},
            {"name": "轻松散步", "duration_min": 15, "intensity": "low", "reason": "促进恢复，不必额外消耗过多热量"},
        ]
        exercise_note = "增肌期不要把热量缺口拉大，训练后及时补充蛋白质和主食。"
    else:
        exercise = [
            {"name": "快走", "duration_min": 30, "intensity": "moderate", "reason": "帮助餐后血糖和热量平衡"},
            {"name": "全身拉伸", "duration_min": 10, "intensity": "low", "reason": "放松肌肉，保持活动度"},
        ]
        exercise_note = "保持目标下，规律活动比一次性高强度更重要。"

    return {
        "meal_type": meal_type,
        "meal_label": meal_label,
        "summary": summary,
        "target_calories": meal_target,
        "dishes": dishes,
        "meal_tips": [
            "先吃蔬菜和蛋白质，再吃主食。",
            "晚餐与睡觉间隔至少 2-3 小时。",
            "根据当天活动量和身体感受调整份量。",
        ],
        "exercise": exercise,
        "exercise_note": exercise_note,
        "note": "热量与运动建议为估算值，仅供参考，不构成医疗建议。",
    }


async def recommend_meal(
    profile: dict,
    daily: dict,
    meal_type: str,
    logs: list[dict],
) -> tuple[dict, str]:
    if settings.mock_mode:
        return _mock_meal_recommendation(daily, profile, meal_type), "mock"

    meal_label = MEAL_LABELS.get(meal_type, "用餐")
    compact_logs = [
        {
            "餐次": MEAL_LABELS.get(log.get("meal_type"), "用餐"),
            "描述": log.get("description") or "",
            "热量": log.get("calories") or 0,
            "蛋白质": log.get("protein") or 0,
            "脂肪": log.get("fat") or 0,
            "碳水": log.get("carbs") or 0,
        }
        for log in logs
    ]
    user_prompt = json.dumps(
        {
            "体重kg": profile.get("weight_kg"),
            "目标": profile.get("goal"),
            "每日推荐热量": daily.get("target"),
            "今日已摄入": daily.get("totals"),
            "剩余": daily.get("remaining"),
            "已记录餐次": daily.get("recorded_meals") or [],
            "饮食明细": compact_logs,
            "今日运动": (daily.get("exercise") or {}).get("today"),
            "热量缺口": daily.get("energy_balance"),
            "下一餐": meal_label,
            "要求": "只根据以上热量、营养物质、体重、目标、今日运动和热量缺口，直接推荐下一餐和今天还可做的运动。",
        },
        ensure_ascii=False,
    )
    data = await chat_json(
        MEAL_RECOMMEND_SYSTEM_PROMPT, user_prompt, temperature=0.4
    )
    return _normalize_meal_recommendation(data, meal_type), "deepseek"


def _mock_chat_reply(message: str, context: dict) -> str:
    totals = context.get("today_diet") or {}
    balance = context.get("energy_balance") or {}
    intake = int(float(totals.get("calories") or 0))
    deficit = int(balance.get("deficit") or 0)
    exercise = context.get("exercise_today") or {}
    exercise_min = int(float(exercise.get("duration_min") or 0))
    exercise_cal = int(float(exercise.get("calories") or 0))
    remaining = context.get("remaining") or {}
    remaining_cal = int(float(remaining.get("calories") or 0))
    text = message.lower()

    if any(word in message for word in ("晚餐", "吃什么", "食谱", "下一餐", "加餐")):
        suggestion = (
            f"今天已摄入约 {intake} 千卡，剩余额度约 {remaining_cal} 千卡，"
            f"热量缺口约 {deficit} 千卡。下一餐建议优先蛋白质和蔬菜，"
            "例如清蒸鱼/鸡胸肉 + 一份深色蔬菜 + 小份杂粮饭；如果额度不多，就选豆腐蔬菜汤。"
        )
    elif any(word in message for word in ("运动", "跑步", "训练", "消耗")):
        suggestion = (
            f"今天已运动 {exercise_min} 分钟、消耗约 {exercise_cal} 千卡，"
            f"当前热量缺口约 {deficit} 千卡。可以饭后快走 20-30 分钟，"
            "或做 15 分钟自重力量训练；如果已经运动超过 30 分钟，优先拉伸和恢复。"
        )
    elif any(word in message for word in ("蛋白", "营养", "碳水", "脂肪", "纤维")):
        suggestion = (
            f"今天蛋白质约 {round(float(totals.get('protein') or 0))}g、"
            f"脂肪约 {round(float(totals.get('fat') or 0))}g、"
            f"碳水约 {round(float(totals.get('carbs') or 0))}g、"
            f"纤维约 {round(float(totals.get('fiber') or 0))}g。"
            "下一餐可以补一份优质蛋白和一份蔬菜，主食控制在一拳头左右。"
        )
    else:
        suggestion = (
            f"根据今天的数据：已摄入 {intake} 千卡，运动消耗 {exercise_cal} 千卡，"
            f"热量缺口约 {deficit} 千卡。你可以问我“晚餐吃什么”“今天还适合做什么运动”"
            "或“蛋白质够不够”。"
        )
    return suggestion + " 以上为估算建议，不构成医疗建议。"


async def chat_text(
    system: str,
    messages: list[dict],
    context: dict | None = None,
    temperature: float = 0.6,
) -> str:
    if settings.mock_mode:
        return _mock_chat_reply(
            messages[-1]["content"] if messages else "",
            context or {},
        )
    chat_messages = [{"role": "system", "content": system}]
    for item in messages:
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            chat_messages.append({"role": role, "content": content})
    return await _chat_completion(
        chat_messages,
        temperature=temperature,
        json_mode=False,
        max_tokens=1500,
    )


async def test_connection() -> tuple[bool, str]:
    if settings.mock_mode:
        return False, "尚未配置 API Key，当前为本地模式"
    try:
        content = await _chat_completion(
            [{"role": "user", "content": "只回复 OK"}],
            temperature=0.0,
            json_mode=False,
            max_tokens=8,
        )
        return True, (content or "").strip()[:100] or "连接正常"
    except AIError as exc:
        return False, str(exc)

