"""小米账号登录（passport → 米健康 serviceToken）。

改编自 Aaron-gx/mihealth-api（MIT License）。
密码只在登录请求中使用；本项目会按用户选择加密保存在本机。
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import string
import time
from urllib.parse import parse_qs, urlparse

import requests

ACCOUNT_HOST = "https://account.xiaomi.com"
SID_HEALTH = "miothealth"
SDK_VERSION = "accountsdk-18.8.15"
AGENT = "XiaomiHealthApi-ABCDE APP/com.xiaomi.mihome APPV/10.5.201"
IDENTITY = "https://account.xiaomi.com/identity"
UA_APP = (
    "MiHome/11.3.203 (com.xiaomi.mihome; build:11.3.203; Android 9) "
    "APP/com.xiaomi.mihome APPV/11.3.203 DeviceId/{dev} UserId/{uid} "
    "Platform/Android Region/CN L/zh_CN"
)


class LoginError(Exception):
    def __init__(self, message, code=None, captcha_url=None, raw=None):
        super().__init__(message)
        self.code = code
        self.captcha_url = captcha_url
        self.raw = raw or {}


class Need2FA(LoginError):
    def __init__(self, notification_url, raw=None):
        super().__init__("账号需要二次验证（2FA）", raw=raw)
        self.notification_url = notification_url


def _json_body(text: str) -> dict:
    index = (text or "").find("{")
    if index < 0:
        return {}
    try:
        return json.loads(text[index:])
    except Exception:
        return {}


def _req(session, method, url, tries=3, **kwargs):
    kwargs.setdefault("timeout", 25)
    last_error = None
    for attempt in range(tries):
        try:
            return getattr(session, method)(url, **kwargs)
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(1 + attempt)
    raise LoginError(
        f"网络请求失败（{tries} 次）：{type(last_error).__name__}: {last_error}"
    )


def md5_upper(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest().upper()


def hash_password(password: str) -> str:
    return md5_upper(password)


def _device_id() -> str:
    return "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(16))


def _session(proxies=None, device_id=None) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {"User-Agent": AGENT, "Content-Type": "application/x-www-form-urlencoded"}
    )
    for domain in ("mi.com", "xiaomi.com"):
        session.cookies.set("sdkVersion", SDK_VERSION, domain=domain)
        if device_id:
            session.cookies.set("deviceId", device_id, domain=domain)
    if proxies:
        session.proxies.update(proxies)
    return session


def new_login_session(proxies=None, device_id=None) -> requests.Session:
    device = device_id or _device_id()
    session = _session(proxies, device)
    session.__dict__["_mih_device_id"] = md5_upper(device)
    return session


def _identity_headers(session) -> dict:
    device = session.__dict__.get("_mih_device_id") or ""
    user = session.__dict__.get("_mih_user_id") or ""
    return {
        "User-Agent": UA_APP.format(dev=device, uid=user),
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://account.xiaomi.com/",
    }


def _identity_cookies(session) -> dict:
    device = session.__dict__.get("_mih_device_id")
    return {"deviceId": device} if device else {}


def _id_call(session, method, url, step, **kwargs):
    kwargs.setdefault("headers", _identity_headers(session))
    kwargs.setdefault("cookies", _identity_cookies(session))
    response = _req(session, method, url, **kwargs)
    text = (response.text or "").strip()
    if not text:
        raise LoginError(
            f"[{step}] 服务端返回空响应（HTTP {response.status_code}）"
        )
    return response


def login_with_password(
    username: str,
    password: str,
    sid: str = SID_HEALTH,
    captcha: str | None = None,
    ick: str | None = None,
    device_id: str | None = None,
    proxies=None,
    locale: str = "zh_CN",
    session=None,
) -> dict:
    session = session or new_login_session(proxies, device_id)
    first = _req(
        session,
        "get",
        f"{ACCOUNT_HOST}/pass/serviceLogin",
        params={"sid": sid, "_json": "true"},
        cookies={"userId": username},
    )
    first_json = _json_body(first.text)
    if not first_json.get("_sign"):
        raise LoginError(f"serviceLogin 未返回 _sign（HTTP {first.status_code}）", raw=first_json)

    fields = {
        "user": username,
        "hash": hash_password(password),
        "sid": sid,
        "_json": "true",
        "_sign": first_json["_sign"],
        "qs": first_json.get("qs") or f"?sid={sid}&_json=true",
        "callback": first_json.get("callback") or "",
        "locale": locale,
    }
    if captcha:
        fields["captCode"] = captcha
    cookies = {"ick": ick} if ick else {}
    second = _req(
        session,
        "post",
        f"{ACCOUNT_HOST}/pass/serviceLoginAuth2",
        params=fields,
        cookies=cookies,
        allow_redirects=False,
    )
    second_json = _json_body(second.text)

    if second_json.get("captchaUrl"):
        raise LoginError(
            "需要图片验证码",
            code=second_json.get("code"),
            captcha_url=second_json["captchaUrl"],
            raw=second_json,
        )
    if not (
        isinstance(second_json.get("ssecurity"), str)
        and len(second_json["ssecurity"]) > 4
    ):
        if second_json.get("notificationUrl"):
            raise Need2FA(second_json["notificationUrl"], raw=second_json)
        raise LoginError(
            second_json.get("desc") or f"登录失败 code={second_json.get('code')}",
            code=second_json.get("code"),
            raw=second_json,
        )

    token = None
    if second_json.get("location"):
        third = _req(session, "get", second_json["location"], allow_redirects=True)
        token = (
            session.cookies.get("serviceToken", domain="sts-hlth.io.mi.com")
            or session.cookies.get("serviceToken")
        )
        if not token:
            match = re.search(r"serviceToken=([^;]+)", third.headers.get("Set-Cookie", ""))
            token = match.group(1) if match else None
    return {
        "ssecurity": second_json.get("ssecurity"),
        "service_token": token,
        "cuser_id": second_json.get("cUserId"),
        "user_id": second_json.get("userId"),
        "pass_token": second_json.get("passToken"),
        "sid": sid,
        "ts": int(time.time()),
    }


def exchange_pass_token(
    pass_token: str,
    cuser_id: str,
    user_id,
    sid: str = SID_HEALTH,
    proxies=None,
) -> dict:
    session = _session(proxies)
    cookies = {
        "passToken": pass_token,
        "cUserId": cuser_id,
        "userId": "" if user_id is None else str(user_id),
    }
    for key, value in cookies.items():
        if value:
            session.cookies.set(key, value, domain=".account.xiaomi.com")
    response = _req(
        session,
        "get",
        f"{ACCOUNT_HOST}/pass/serviceLogin",
        params={"sid": sid, "_json": "true"},
        cookies=cookies,
    )
    payload = _json_body(response.text)
    if payload.get("code") != 0 or not payload.get("location"):
        raise LoginError(
            f"passToken 无效或已过期（code={payload.get('code')} {payload.get('desc')}）",
            raw=payload,
        )
    callback = _req(session, "get", payload["location"], cookies=cookies, allow_redirects=False)
    token = (
        session.cookies.get("serviceToken", domain="sts-hlth.io.mi.com")
        or session.cookies.get("serviceToken")
    )
    if not token:
        match = re.search(r"serviceToken=([^;]+)", callback.headers.get("Set-Cookie", ""))
        token = match.group(1) if match else None
    if not token:
        raise LoginError("STS 回调未返回 serviceToken")
    return {
        "ssecurity": payload.get("ssecurity"),
        "service_token": token,
        "cuser_id": payload.get("cUserId") or cuser_id,
        "user_id": payload.get("userId") or user_id,
        "sid": sid,
        "ts": int(time.time()),
    }


def start_2fa(session, notification_url: str, sid: str = SID_HEALTH, locale: str = "zh_CN") -> dict:
    if not notification_url.startswith("http"):
        notification_url = ACCOUNT_HOST + notification_url
    _id_call(session, "get", notification_url, "authStart")
    query = parse_qs(urlparse(notification_url).query)
    context = (query.get("context") or [""])[0]
    sid = (query.get("sid") or [sid])[0]
    if query.get("userId"):
        session.__dict__["_mih_user_id"] = query["userId"][0]

    response = _id_call(
        session,
        "get",
        f"{IDENTITY}/list",
        "identity/list",
        params={"sid": sid, "supportedMask": "0", "_locale": locale, "context": context},
    )
    identity = _json_body(response.text)
    flag = identity.get("flag", 4)
    method = "Email" if flag == 8 else "Phone"

    _id_call(
        session,
        "get",
        f"{IDENTITY}/auth/verify{method}",
        f"verify{method}(trigger)",
        params={"_flag": str(flag), "_json": "true"},
    )
    if method == "Phone":
        _id_call(
            session,
            "post",
            f"{IDENTITY}/auth/sendPhoneTicket",
            "sendPhoneTicket",
            data={"retry": "0", "icode": "", "_json": "true"},
        )

    hint = ""
    for key in ("mask", "notification", "email", "phone", "address"):
        if identity.get(key):
            hint = identity[key]
            break
    return {"context": context, "flag": flag, "method": method, "hint": hint, "raw": identity}


def _location_from(response) -> str | None:
    """从响应头、JSON、嵌套 JSON 或正文中提取下一步跳转地址。"""
    if response is None:
        return None
    header_location = response.headers.get("Location")
    if header_location:
        return header_location
    try:
        payload = response.json() or {}
    except Exception:
        payload = {}
    for key in ("location", "url", "redirectUrl"):
        if payload.get(key):
            return payload[key]
    for key in ("data", "result"):
        nested = payload.get(key)
        if isinstance(nested, dict) and nested.get("location"):
            return nested["location"]
    match = re.search(
        r"https://account\.xiaomi\.com/(?:identity/result/check|"
        r"pass/serviceLoginAuth2/end)\?[^\"'\s]+",
        response.text or "",
    )
    return match.group(0) if match else None


def _extract_ssecurity(response) -> str | None:
    header = response.headers.get("extension-pragma")
    if header:
        try:
            parsed = json.loads(header)
            if isinstance(parsed, dict) and parsed.get("ssecurity"):
                return parsed["ssecurity"]
        except Exception:
            pass
    try:
        cookie_value = response.cookies.get("ssecurity")
        if cookie_value:
            return cookie_value
    except Exception:
        pass
    text = response.text or ""
    match = re.search(r'"ssecurity"\s*:\s*"([^"]+)"', text)
    if match:
        return match.group(1)
    match = re.search(r"ssecurity=([^;,\s]+)", response.headers.get("Set-Cookie", ""))
    return match.group(1) if match else None


def _extract_sts_location(response) -> str | None:
    location = response.headers.get("Location")
    if location and "sts" in location:
        return location
    text = response.text or ""
    match = re.search(r"https://sts[^\s\"'<>]+", text)
    return match.group(0) if match else None


def _sts_token(session, sts_url: str | None) -> str | None:
    if not sts_url:
        return None
    if sts_url.startswith("//"):
        sts_url = "https:" + sts_url
    elif sts_url.startswith("/"):
        sts_url = "https://sts-hlth.io.mi.com" + sts_url
    response = _req(session, "get", sts_url, allow_redirects=True)
    token = (
        session.cookies.get("serviceToken", domain="sts-hlth.io.mi.com")
        or session.cookies.get("serviceToken")
    )
    if token:
        return token
    match = re.search(r"serviceToken=([^;]+)", response.headers.get("Set-Cookie", ""))
    return match.group(1) if match else None


def finish_2fa(
    session,
    code: str,
    context: str,
    flag: int = 4,
    sid: str = SID_HEALTH,
    locale: str = "zh_CN",
) -> dict:
    """提交二次验证码，并重新走 serviceLogin/STS 换取凭据。"""
    method = "Email" if flag == 8 else "Phone"
    response = _id_call(
        session,
        "post",
        f"{IDENTITY}/auth/verify{method}",
        f"verify{method}(submit)",
        params={
            "_dc": str(int(time.time() * 1000)),
            "_flag": str(flag),
            "_json": "true",
            "sid": sid,
            "context": context,
        },
        data={
            "_flag": str(flag),
            "ticket": code.strip(),
            "trust": "false",
            "_json": "true",
        },
    )
    payload = _json_body(response.text)
    if payload.get("code") not in (0, None) and not payload.get("location"):
        raise LoginError(
            "验证码校验未通过"
            f"（code={payload.get('code')} {payload.get('desc') or ''}）。"
            "请确认验证码来自当前通道、没有过期；如果账号要求其他安全验证，"
            "请先在小米运动健康 App 内完成验证。",
            code=payload.get("code"),
            raw=payload,
        )

    location = payload.get("location") or response.headers.get("Location")
    if not location:
        match = re.search(r"location\s*[:=]\s*[\"']([^\"']+)", response.text or "")
        location = match.group(1) if match else None
    if not location:
        snippet = (response.text or "")[:300]
        raise LoginError(
            f"验证码校验后未拿到跳转地址（HTTP {response.status_code}，响应：{snippet!r}）",
            code=payload.get("code"),
            raw=payload,
        )
    if not location.startswith("http"):
        location = ACCOUNT_HOST + location

    # 先访问验证后的跳转地址，让会话变成已认证状态
    _req(session, "get", location, allow_redirects=True)

    # 重新走一次 serviceLogin，此时应返回 ssecurity / passToken / STS 地址
    third = _req(
        session,
        "get",
        f"{ACCOUNT_HOST}/pass/serviceLogin",
        params={"sid": sid, "_json": "true"},
    )
    third_json = _json_body(third.text)
    if third_json.get("code") != 0 or not third_json.get("ssecurity"):
        raise LoginError(
            "二次验证后登录未完成"
            f"（code={third_json.get('code')} {third_json.get('desc') or ''}）。"
            "请重新连接；如果仍失败，请先在小米运动健康 App 内完成安全验证。",
            code=third_json.get("code"),
            raw=third_json,
        )

    token = None
    if third_json.get("location"):
        fourth = _req(
            session,
            "get",
            third_json["location"],
            allow_redirects=False,
        )
        token = (
            session.cookies.get("serviceToken", domain="sts-hlth.io.mi.com")
            or session.cookies.get("serviceToken")
        )
        if not token:
            match = re.search(
                r"serviceToken=([^;]+)", fourth.headers.get("Set-Cookie", "")
            )
            token = match.group(1) if match else None

    if not token:
        raise LoginError(
            "二次验证已完成，但未取得米健康 serviceToken。"
            "请重新点击连接；若仍失败，请检查账号地区是否为大陆/海外。",
            code=third_json.get("code"),
            raw=third_json,
        )

    return {
        "ssecurity": third_json.get("ssecurity"),
        "service_token": token,
        "cuser_id": third_json.get("cUserId") or session.cookies.get("cUserId"),
        "user_id": third_json.get("userId") or session.cookies.get("userId"),
        "pass_token": third_json.get("passToken")
        or session.cookies.get("passToken"),
        "sid": sid,
        "ts": int(time.time()),
    }
