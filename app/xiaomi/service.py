"""小米运动健康直连：登录、会话刷新、同步到 ShyHealthHelper 数据库。"""

from __future__ import annotations

import base64
import json
import threading
import time
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from ..db import get_db
from ..routers.body import sync_profile_weight, upsert_body_record
from .client import ApiError, AuthError, MiHealthClient
from .login import (
    ACCOUNT_HOST,
    LoginError,
    Need2FA,
    exchange_pass_token,
    finish_2fa,
    login_with_password,
    new_login_session,
    start_2fa,
)
from .store import store

DEFAULT_ZONE_OFFSET = 8 * 3600
MAX_SYNC_DAYS = 90

_PENDING: dict[str, dict] = {}
_PENDING_LOCK = threading.Lock()
_PENDING_LIMIT = 8
_SYNC_LOCK = threading.Lock()


class XiaomiError(Exception):
    pass


class NotConnectedError(XiaomiError):
    pass


def status() -> dict:
    data = store.load()
    connected = bool(data.get("service_token") and data.get("ssecurity"))
    return {
        "connected": connected,
        "username": data.get("username"),
        "region": data.get("region") or "cn",
        "last_sync": data.get("last_sync"),
        "last_login": data.get("last_login"),
        "last_result": data.get("last_result") or {},
        "has_password": bool(data.get("password")),
        "has_pass_token": bool(data.get("pass_token")),
        "session_at": data.get("session_at"),
    }


def _remember_pending(payload: dict) -> str:
    attempt_id = uuid4().hex
    with _PENDING_LOCK:
        if len(_PENDING) >= _PENDING_LIMIT:
            oldest = next(iter(_PENDING))
            _PENDING.pop(oldest, None)
        _PENDING[attempt_id] = payload
    return attempt_id


def _take_pending(attempt_id: str) -> dict | None:
    with _PENDING_LOCK:
        return _PENDING.get(attempt_id)


def _drop_pending(attempt_id: str) -> None:
    with _PENDING_LOCK:
        _PENDING.pop(attempt_id, None)


def _store_session(tokens: dict, username: str, password: str, region: str, device_id: str) -> dict:
    if not tokens.get("service_token") or not tokens.get("ssecurity"):
        raise XiaomiError("登录失败：未获取到米健康 serviceToken，请稍后重试")
    data = store.load()
    data.update(
        {
            "username": username,
            "password": password,
            "region": region or "cn",
            "device_id": device_id,
            "ssecurity": tokens.get("ssecurity"),
            "service_token": tokens.get("service_token"),
            "cuser_id": tokens.get("cuser_id"),
            "user_id": tokens.get("user_id"),
            "pass_token": tokens.get("pass_token") or data.get("pass_token"),
            "session_at": int(time.time()),
            "last_login": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    store.save(data)
    return status()


def _captcha_challenge(
    session,
    exc: LoginError,
    username: str,
    password: str,
    region: str,
    device_id: str,
) -> dict:
    url = exc.captcha_url or ""
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = ACCOUNT_HOST + url
    image = None
    if url:
        try:
            response = session.get(url, timeout=20)
            if response.ok:
                mime = response.headers.get("Content-Type", "image/jpeg").split(";")[0]
                encoded = base64.b64encode(response.content).decode("ascii")
                image = f"data:{mime};base64,{encoded}"
        except Exception:
            image = None
    ick = session.cookies.get("ick")
    attempt_id = _remember_pending(
        {
            "kind": "captcha",
            "session": session,
            "username": username,
            "password": password,
            "region": region,
            "device_id": device_id,
            "ick": ick,
        }
    )
    return {
        "status": "need_captcha",
        "attempt_id": attempt_id,
        "captcha_image": image,
        "captcha_url": url,
        "message": "小米账号需要图片验证码，请输入图片中的字符后继续。",
    }


def _twofa_challenge(
    session,
    exc: Need2FA,
    username: str,
    password: str,
    region: str,
    device_id: str,
) -> dict:
    try:
        info = start_2fa(session, exc.notification_url)
    except LoginError as start_error:
        raise XiaomiError(f"发送二次验证码失败：{start_error}") from start_error
    attempt_id = _remember_pending(
        {
            "kind": "2fa",
            "session": session,
            "context": info["context"],
            "flag": info["flag"],
            "method": info["method"],
            "hint": info.get("hint") or "",
            "username": username,
            "password": password,
            "region": region,
            "device_id": device_id,
        }
    )
    channel = "邮箱" if info["method"] == "Email" else "手机短信"
    return {
        "status": "need_2fa",
        "attempt_id": attempt_id,
        "method": info["method"],
        "method_label": channel,
        "hint": info.get("hint") or "",
        "message": f"验证码已发送到你的{channel}，请输入验证码完成连接。",
    }


def login(
    username: str,
    password: str,
    region: str = "cn",
    captcha: str | None = None,
    twofa_code: str | None = None,
    attempt_id: str | None = None,
) -> dict:
    username = username.strip()
    region = region if region in {"cn", "abroad"} else "cn"

    if attempt_id:
        pending = _take_pending(attempt_id)
        if not pending:
            raise XiaomiError("登录会话已过期，请重新输入账号密码")
        session = pending["session"]
        if twofa_code:
            if pending.get("kind") != "2fa":
                raise XiaomiError("当前登录会话不需要二次验证码")
            try:
                tokens = finish_2fa(
                    session,
                    twofa_code,
                    pending["context"],
                    pending["flag"],
                )
            except LoginError as exc:
                raise XiaomiError(str(exc)) from exc
            _drop_pending(attempt_id)
            return _store_session(
                tokens,
                pending["username"],
                pending["password"],
                pending["region"],
                pending["device_id"],
            )
        username = pending["username"]
        password = pending["password"]
        region = pending["region"]
        device_id = pending["device_id"]
        try:
            tokens = login_with_password(
                username,
                password,
                captcha=captcha,
                ick=pending.get("ick"),
                device_id=device_id,
                session=session,
            )
        except Need2FA as exc:
            return _twofa_challenge(session, exc, username, password, region, device_id)
        except LoginError as exc:
            if exc.captcha_url:
                return _captcha_challenge(session, exc, username, password, region, device_id)
            raise XiaomiError(str(exc)) from exc
        _drop_pending(attempt_id)
        return _store_session(tokens, username, password, region, device_id)

    if not username or not password:
        raise XiaomiError("请输入小米账号和密码")

    existing = store.load()
    device_id = existing.get("device_id") or uuid4().hex.upper()[:16]
    session = new_login_session(device_id=device_id)
    try:
        tokens = login_with_password(
            username,
            password,
            device_id=device_id,
            session=session,
        )
    except Need2FA as exc:
        return _twofa_challenge(session, exc, username, password, region, device_id)
    except LoginError as exc:
        if exc.captcha_url:
            return _captcha_challenge(session, exc, username, password, region, device_id)
        raise XiaomiError(str(exc)) from exc
    return _store_session(tokens, username, password, region, device_id)


def logout() -> dict:
    store.clear()
    with _PENDING_LOCK:
        _PENDING.clear()
    return {"connected": False}


def _client(credentials: dict) -> MiHealthClient:
    return MiHealthClient(
        credentials["ssecurity"],
        credentials["service_token"],
        credentials["cuser_id"],
        region=credentials.get("region") or "cn",
        min_interval=0.25,
    )


def _refresh_session(credentials: dict) -> dict:
    try:
        tokens = exchange_pass_token(
            credentials.get("pass_token") or "",
            credentials.get("cuser_id") or "",
            credentials.get("user_id"),
        )
        if not tokens.get("service_token") or not tokens.get("ssecurity"):
            raise XiaomiError("免密续期未返回有效凭据")
        credentials.update(
            {
                "ssecurity": tokens.get("ssecurity"),
                "service_token": tokens.get("service_token"),
                "cuser_id": tokens.get("cuser_id") or credentials.get("cuser_id"),
                "user_id": tokens.get("user_id") or credentials.get("user_id"),
                "session_at": int(time.time()),
            }
        )
        store.save(credentials)
        return credentials
    except Exception:
        pass

    password = credentials.get("password")
    if not password:
        raise XiaomiError("小米登录态已过期，且没有保存密码，请重新连接账号")
    session = new_login_session(device_id=credentials.get("device_id"))
    try:
        tokens = login_with_password(
            credentials.get("username") or "",
            password,
            device_id=credentials.get("device_id"),
            session=session,
        )
    except Need2FA as exc:
        raise XiaomiError(
            "小米登录态已过期，重新登录需要二次验证，请在页面重新连接账号"
        ) from exc
    except LoginError as exc:
        if exc.captcha_url:
            raise XiaomiError(
                "小米登录态已过期，重新登录需要图片验证码，请在页面重新连接账号"
            ) from exc
        raise XiaomiError(f"小米账号重新登录失败：{exc}") from exc
    _store_session(
        tokens,
        credentials.get("username") or "",
        password,
        credentials.get("region") or "cn",
        credentials.get("device_id") or "",
    )
    return store.load()


def _parse_value(item: dict) -> dict:
    raw = item.get("value")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("{"):
            try:
                data = json.loads(text)
                return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}


def _number(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:
        return None
    return result


def _local_date(timestamp, offset: int = DEFAULT_ZONE_OFFSET) -> date | None:
    value = _number(timestamp)
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone(timedelta(seconds=offset))).date()


def _local_time(timestamp, offset: int = DEFAULT_ZONE_OFFSET) -> str | None:
    value = _number(timestamp)
    if value is None:
        return None
    moment = datetime.fromtimestamp(value, tz=timezone(timedelta(seconds=offset)))
    return moment.strftime("%H:%M")


ACTIVITY_KEYWORDS = (
    ("run", "跑步"),
    ("walk", "步行"),
    ("hike", "徒步"),
    ("cycl", "骑行"),
    ("bike", "骑行"),
    ("swim", "游泳"),
    ("strength", "力量训练"),
    ("yoga", "瑜伽"),
    ("rope", "跳绳"),
    ("skip", "跳绳"),
    ("basketball", "篮球"),
    ("football", "足球"),
    ("soccer", "足球"),
    ("badminton", "羽毛球"),
    ("table_tennis", "乒乓球"),
    ("elliptical", "椭圆机"),
    ("row", "划船"),
    ("dance", "舞蹈"),
    ("climb", "爬楼"),
)


def _activity_name(key: str, value: dict) -> str:
    text = f"{key} {value.get('sport_type') or ''}".lower()
    for keyword, label in ACTIVITY_KEYWORDS:
        if keyword in text:
            return label
    sport_type = value.get("sport_type")
    if isinstance(sport_type, str) and sport_type.strip() and not sport_type.isdigit():
        return sport_type.strip()[:40]
    return (key or "运动").replace("_", " ")[:40]


def _extract_steps(items: list[dict]) -> dict[str, dict]:
    daily: dict[str, dict] = {}
    for item in items:
        value = _parse_value(item)
        offset = int(_number(item.get("zone_offset")) or DEFAULT_ZONE_OFFSET)
        record_date = _local_date(item.get("time"), offset)
        if record_date is None:
            continue
        steps = _number(value.get("steps") if value.get("steps") is not None else item.get("steps"))
        if steps is None:
            continue
        bucket = daily.setdefault(record_date.isoformat(), {"steps": 0.0, "calories": 0.0})
        bucket["steps"] += max(0.0, steps)
        calories = _number(value.get("calories"))
        if calories:
            bucket["calories"] += max(0.0, calories)
    return daily


WEIGHT_KEYS = ("weight", "weight_kg", "body_weight")
BODY_FAT_KEYS = (
    "body_fat",
    "body_fat_rate",
    "bodyfat",
    "fat_rate",
    "body_fat_percentage",
)
MUSCLE_KEYS = ("muscle_mass", "muscle_kg", "muscle")
WAIST_KEYS = ("waist", "waistline", "waist_cm")


def _first_number(value: dict, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        number = _number(value.get(key))
        if number is not None:
            return number
    return None


def _extract_weight(items: list[dict]) -> dict[str, dict]:
    daily: dict[str, dict] = {}
    for item in items:
        value = _parse_value(item)
        offset = int(_number(item.get("zone_offset")) or DEFAULT_ZONE_OFFSET)
        timestamp = value.get("time") or value.get("measure_time") or item.get("time")
        record_date = _local_date(timestamp, offset)
        if record_date is None:
            continue
        weight = _first_number(value, WEIGHT_KEYS)
        if weight is None:
            weight = _first_number(item, WEIGHT_KEYS)
        raw_value = item.get("value")
        if weight is None and isinstance(raw_value, (int, float)):
            weight = float(raw_value)
        body_fat = _first_number(value, BODY_FAT_KEYS)
        muscle = _first_number(value, MUSCLE_KEYS)
        waist = _first_number(value, WAIST_KEYS)
        if weight is None and body_fat is None and muscle is None and waist is None:
            continue
        daily[record_date.isoformat()] = {
            "weight_kg": weight,
            "body_fat_pct": body_fat,
            "muscle_kg": muscle,
            "waist_cm": waist,
        }
    return daily


def _extract_sleep(items: list[dict]) -> dict[str, dict]:
    daily: dict[str, dict] = {}
    for item in items:
        value = _parse_value(item)
        offset = int(_number(item.get("zone_offset")) or DEFAULT_ZONE_OFFSET)
        bedtime = value.get("bedtime") or item.get("time")
        deep = _number(value.get("sleep_deep_duration")) or 0.0
        light = _number(value.get("sleep_light_duration")) or 0.0
        rem = _number(value.get("sleep_rem_duration")) or 0.0
        duration_seconds = _number(value.get("duration"))
        minutes = deep + light + rem
        if minutes <= 0 and duration_seconds:
            minutes = duration_seconds / 60
        if minutes <= 0:
            continue
        wake = (
            value.get("device_wake_up_time")
            or value.get("wake_up_time")
            or value.get("wake_time")
        )
        if wake is None and bedtime is not None and duration_seconds:
            wake = _number(bedtime) + duration_seconds
        record_date = _local_date(wake if wake is not None else bedtime, offset)
        if record_date is None:
            continue
        bucket = daily.setdefault(record_date.isoformat(), {"minutes": 0.0})
        bucket["minutes"] += minutes
    return daily


def _log_exists(db, log: dict) -> bool:
    row = db.execute(
        "SELECT id FROM exercise_logs WHERE source = 'xiaomi' AND log_date = ? "
        "AND activity = ? AND IFNULL(start_time, '') = IFNULL(?, '') "
        "AND IFNULL(duration_min, -1) = IFNULL(?, -1) "
        "AND IFNULL(distance_km, -1) = IFNULL(?, -1)",
        (
            log.get("log_date"),
            log.get("activity"),
            log.get("start_time"),
            log.get("duration_min"),
            log.get("distance_km"),
        ),
    ).fetchone()
    return row is not None


def _extract_sport(items: list[dict]) -> list[dict]:
    logs = []
    for item in items:
        value = _parse_value(item)
        offset = int(_number(item.get("zone_offset")) or DEFAULT_ZONE_OFFSET)
        start_ts = value.get("start_time") or item.get("time")
        record_date = _local_date(start_ts, offset)
        if record_date is None:
            continue
        duration = _number(value.get("duration")) or _number(value.get("duration_s"))
        distance = _number(value.get("distance"))
        calories = _number(value.get("calories")) or _number(value.get("total_cal"))
        heart_rate = _number(value.get("avg_hrm")) or _number(value.get("avg_hr"))
        steps = _number(value.get("steps"))
        key = str(item.get("key") or "")
        logs.append(
            {
                "log_date": record_date.isoformat(),
                "start_time": _local_time(start_ts, offset),
                "activity": _activity_name(key, value),
                "duration_min": round(duration / 60, 1) if duration else None,
                "calories": round(calories, 1) if calories else None,
                "distance_km": round(distance / 1000, 2) if distance else None,
                "steps": int(steps) if steps else None,
                "avg_heart_rate": int(heart_rate) if heart_rate else None,
                "notes": "小米运动健康直连同步",
                "raw": value or item,
            }
        )
    return logs


def _insert_sport_log(db, log: dict) -> None:
    db.execute(
        "INSERT INTO exercise_logs "
        "(log_date, start_time, activity, duration_min, calories, distance_km, "
        "steps, avg_heart_rate, notes, source, ai_mode, raw) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'xiaomi', 'direct', ?)",
        (
            log["log_date"],
            log.get("start_time"),
            log.get("activity") or "运动",
            log.get("duration_min"),
            log.get("calories"),
            log.get("distance_km"),
            log.get("steps"),
            log.get("avg_heart_rate"),
            log.get("notes") or "",
            json.dumps(log.get("raw") or {}, ensure_ascii=False),
        ),
    )


def _sync_from_client(client: MiHealthClient, start_ms: int, end_ms: int, days: int) -> dict:
    result = {
        "steps_days": 0,
        "weight_records": 0,
        "sleep_days": 0,
        "sport_records": 0,
        "errors": [],
    }

    steps_items: list[dict] = []
    weight_items: list[dict] = []
    sleep_items: list[dict] = []
    sport_items: list[dict] = []
    max_pages = max(60, min(600, days * 12))

    for key, bucket, pages in (
        ("steps", steps_items, max_pages),
        ("weight", weight_items, 60),
        ("sleep", sleep_items, 60),
    ):
        try:
            response = client.get_fitness_data_all(key, start_ms, end_ms, max_pages=pages)
            bucket.extend(response.get("data_list") or [])
        except AuthError:
            raise
        except ApiError as exc:
            result["errors"].append(f"{key}: {exc}")

    try:
        response = client.get_sport_records_all(start_ms, end_ms, max_pages=100)
        sport_items.extend(response.get("sport_records") or [])
    except AuthError:
        raise
    except ApiError as exc:
        result["errors"].append(f"sport: {exc}")

    steps = _extract_steps(steps_items)
    weights = _extract_weight(weight_items)
    sleep = _extract_sleep(sleep_items)
    sport_logs = _extract_sport(sport_items)

    with get_db() as db:
        for record_date, values in steps.items():
            upsert_body_record(
                db,
                {
                    "record_date": record_date,
                    "steps": int(round(values["steps"])),
                    "source": "xiaomi",
                },
            )
            result["steps_days"] += 1
        for record_date, values in weights.items():
            upsert_body_record(
                db,
                {
                    "record_date": record_date,
                    **values,
                    "notes": "",
                    "source": "xiaomi",
                },
            )
            result["weight_records"] += 1
        for record_date, values in sleep.items():
            upsert_body_record(
                db,
                {
                    "record_date": record_date,
                    "sleep_hours": round(values["minutes"] / 60, 1),
                    "source": "xiaomi",
                },
            )
            result["sleep_days"] += 1
        for log in sport_logs:
            if _log_exists(db, log):
                continue
            _insert_sport_log(db, log)
            result["sport_records"] += 1
        sync_profile_weight(db)

    return result


def sync(days: int = 7) -> dict:
    if not _SYNC_LOCK.acquire(blocking=False):
        raise XiaomiError("同步正在进行中，请稍后再试")
    try:
        credentials = store.load()
        if not credentials.get("service_token") or not credentials.get("ssecurity"):
            raise NotConnectedError("还没有连接小米运动健康账号")
        days = max(1, min(MAX_SYNC_DAYS, int(days)))
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - days * 86400 * 1000

        client = _client(credentials)
        try:
            result = _sync_from_client(client, start_ms, end_ms, days)
        except AuthError:
            credentials = _refresh_session(store.load())
            client = _client(credentials)
            result = _sync_from_client(client, start_ms, end_ms, days)

        credentials = store.load()
        credentials["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        credentials["last_sync_days"] = days
        credentials["last_result"] = result
        store.save(credentials)
        result["days"] = days
        result["last_sync"] = credentials["last_sync"]
        return result
    finally:
        _SYNC_LOCK.release()
