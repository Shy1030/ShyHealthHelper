"""小米运动健康云端 API 客户端（RC4 加密 + SHA1 签名）。

改编自 Aaron-gx/mihealth-api（MIT License），仅保留本项目需要的只读接口。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import random
import struct
import threading
import time
import urllib.parse

import requests


class ApiError(Exception):
    """服务端返回非 0 业务码。"""


class AuthError(ApiError):
    """401 / code=2：登录态过期。"""


def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode()


def b64d(value: str) -> bytes:
    return base64.b64decode(value)


class RC4:
    DROP = 1024

    def __init__(self, key: bytes, drop: int = DROP):
        if len(key) != 32:
            raise ValueError("rc4Key length is invalid")
        state = list(range(256))
        j = 0
        for i in range(256):
            j = (j + state[i] + key[i % len(key)]) & 0xFF
            state[i], state[j] = state[j], state[i]
        self._s = bytearray(state)
        self._i = 0
        self._j = 0
        if drop:
            self._skip(drop)

    def _skip(self, count: int) -> None:
        state, i, j = self._s, self._i, self._j
        for _ in range(count):
            i = (i + 1) & 0xFF
            j = (j + state[i]) & 0xFF
            state[i], state[j] = state[j], state[i]
        self._i, self._j = i, j

    def crypt(self, data: bytes) -> bytes:
        state, i, j = self._s, self._i, self._j
        out = bytearray(len(data))
        for index, byte in enumerate(data):
            i = (i + 1) & 0xFF
            j = (j + state[i]) & 0xFF
            state[i], state[j] = state[j], state[i]
            out[index] = byte ^ state[(state[i] + state[j]) & 0xFF]
        self._i, self._j = i, j
        return bytes(out)


def gen_nonce(time_diff: int = 0) -> str:
    rand8 = random.getrandbits(64).to_bytes(8, "big")
    minutes = int((time.time() * 1000 + time_diff) // 60000)
    return b64e(rand8 + struct.pack(">i", minutes))


def session_key(ssecurity: str, nonce: str) -> str:
    return b64e(hashlib.sha256(b64d(ssecurity) + b64d(nonce)).digest())


def _path_of(path: str) -> str:
    return urllib.parse.urlparse(path).path or path


def sha1_b64(items) -> str:
    return b64e(hashlib.sha1("&".join(items).encode("utf-8")).digest())


def signed_encrypted(method: str, path: str, params: dict, nonce: str, security: str) -> dict:
    skey = session_key(security, nonce)
    plain = {k: v for k, v in params.items() if k and v != "" and v is not None}
    p = _path_of(path)
    rc4_hash = sha1_b64(
        [method.upper(), p]
        + [f"{k}={v}" for k, v in sorted(plain.items())]
        + [skey]
    )
    plain["rc4_hash__"] = rc4_hash
    rc4 = RC4(b64d(skey))
    enc = {k: b64e(rc4.crypt(plain[k].encode("utf-8"))) for k in sorted(plain)}
    signature = sha1_b64(
        [method.upper(), p]
        + [f"{k}={v}" for k, v in enc.items()]
        + [skey]
    )
    out = dict(enc)
    out["signature"] = signature
    out["_nonce"] = nonce
    return out


def decrypt_response(body_b64: str, nonce: str, security: str) -> str:
    return RC4(b64d(session_key(security, nonce))).crypt(b64d(body_b64)).decode("utf-8")


SCALAR_FIELDS = {
    "steps": ("steps",),
    "calories": ("calories",),
    "heart_rate": ("bpm", "heart_rate"),
    "spo2": ("spo2",),
    "stress": ("stress", "stress_value"),
    "vo2_max": ("vo2_max",),
    "pai": ("daily_pai", "pai", "value"),
    "weight": ("weight",),
    "energy": ("energy",),
}


def canonical_number(key: str, item: dict):
    for field in SCALAR_FIELDS.get(key, ()):
        value = item.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None


def dedup_items(items, key=None):
    by_time = {}
    for item in items:
        timestamp = item.get("_t")
        if timestamp is None:
            continue
        current = by_time.get(timestamp)
        if current is None:
            by_time[timestamp] = dict(item)
            continue
        new_num = canonical_number(key or "", item)
        current_num = canonical_number(key or "", current)
        if new_num is not None and (current_num is None or new_num > current_num):
            merged = dict(current)
            merged.update(item)
            by_time[timestamp] = merged
        else:
            for field, value in item.items():
                if field not in current:
                    current[field] = value
    return sorted(by_time.values(), key=lambda item: item["_t"])


class MiHealthClient:
    HOSTS = {
        "cn": "https://hlth.io.mi.com",
        "abroad": "https://region.hlth.io.mi.com",
    }
    PREFIX = "/app/v1/"

    def __init__(
        self,
        ssecurity: str,
        service_token: str,
        cuser_id: str,
        region: str = "cn",
        host: str | None = None,
        time_diff: int = 0,
        proxies: dict | None = None,
        timeout: int = 25,
        max_retries: int = 3,
        min_interval: float = 0.0,
    ):
        self.security = ssecurity
        self.service_token = service_token
        self.cuser = cuser_id
        self.base = (host or self.HOSTS.get(region) or self.HOSTS["cn"]).rstrip("/")
        self.time_diff = time_diff
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0
        self.http = requests.Session()
        if proxies:
            self.http.proxies.update(proxies)

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()

    def _cookies(self) -> dict:
        return {
            "cUserId": self.cuser,
            "serviceToken": self.service_token,
            "locale": "zh_cn",
        }

    def _send(self, method: str, url: str, params: dict, retries: int):
        last_error = None
        for attempt in range(retries + 1):
            self._throttle()
            try:
                if method.upper() == "GET":
                    return self.http.get(
                        url, params=params, cookies=self._cookies(), timeout=self.timeout
                    )
                return self.http.post(
                    url, data=params, cookies=self._cookies(), timeout=self.timeout
                )
            except requests.RequestException as exc:
                last_error = exc
            if attempt < retries:
                time.sleep(min(2 ** attempt + random.random(), 8))
        raise ApiError(f"请求失败（{retries + 1} 次）：{last_error}")

    def call(
        self,
        subpath: str,
        params: dict,
        method: str = "GET",
        decrypt: bool = True,
        retries: int | None = None,
        prefix: str | None = None,
    ):
        retries = self.max_retries if retries is None else retries
        pre = self.PREFIX if prefix is None else prefix
        nonce = gen_nonce(self.time_diff)
        query = signed_encrypted(method, pre + subpath, params, nonce, self.security)
        url = self.base + pre + subpath
        response = self._send(method, url, query, retries)

        if response.status_code in (401, 403):
            raise AuthError(f"登录态已过期（HTTP {response.status_code}）")
        if response.status_code >= 400:
            raise ApiError(f"HTTP {response.status_code}: {response.text[:200]}")
        if not decrypt:
            return response.text
        try:
            data = json.loads(
                decrypt_response(response.text, nonce, self.security)
            )
        except Exception:
            try:
                data = json.loads(response.text)
            except Exception as exc:
                raise ApiError(f"响应解析失败：{response.text[:200]}") from exc

        code = data.get("code")
        if code == 2 or (
            isinstance(code, int) and "auth" in str(data.get("message", "")).lower()
        ):
            raise AuthError(f"登录态已过期（code={code}）")
        return data

    def _paged_all(
        self,
        fetch_page,
        list_field: str,
        start_ms: int,
        end_ms: int,
        max_pages: int,
        stop_below_start: bool,
        key: str | None = None,
    ):
        items = []
        next_key = None

        def timestamp_of(item: dict):
            return item.get("time") or item.get("bedtime") or item.get("start_time")

        for _ in range(max_pages):
            result = (fetch_page(next_key) or {}).get("result") or {}
            batch = result.get(list_field) or []
            for item in batch:
                item.setdefault("_t", timestamp_of(item))
            kept = [
                item
                for item in batch
                if start_ms <= (timestamp_of(item) or 0) * 1000 <= end_ms
            ]
            items.extend(kept)
            next_key = result.get("next_key")
            if not result.get("has_more") or not next_key:
                return dedup_items(items, key), False
            if (
                stop_below_start
                and batch
                and max((timestamp_of(item) or 0) for item in batch) * 1000 < start_ms
            ):
                return dedup_items(items, key), False
        return dedup_items(items, key), True

    def get_fitness_data_by_time(
        self,
        key: str,
        start_ms: int,
        end_ms: int,
        reverse: bool = True,
        next_key: str | None = None,
    ):
        data = {
            "key": key,
            "startTime": start_ms,
            "endTime": end_ms,
            "reverse": reverse,
            "next_key": next_key,
        }
        return self.call(
            "data/get_fitness_data_by_time",
            {"data": json.dumps(data, separators=(",", ":"))},
        )

    def get_fitness_data_all(
        self,
        key: str,
        start_ms: int,
        end_ms: int,
        max_pages: int = 200,
        reverse: bool = True,
    ):
        api_start = max(start_ms, end_ms - 86400000)
        items, more = self._paged_all(
            lambda next_key: self.get_fitness_data_by_time(
                key, api_start, end_ms, reverse, next_key
            ),
            "data_list",
            start_ms,
            end_ms,
            max_pages,
            stop_below_start=True,
            key=key,
        )
        return {"data_list": items, "has_more": more}

    def get_sport_records_by_time(
        self,
        start_ms: int,
        end_ms: int,
        next_key: str | None = None,
        limit: int = 50,
        reverse: bool = True,
    ):
        data = {
            "startTime": start_ms,
            "endTime": end_ms,
            "next_key": next_key,
            "limit": limit,
            "reverse": reverse,
        }
        return self.call(
            "data/get_sport_records_by_time",
            {"data": json.dumps(data, separators=(",", ":"))},
        )

    def get_sport_records_all(
        self,
        start_ms: int,
        end_ms: int,
        max_pages: int = 100,
        limit: int = 50,
        reverse: bool = True,
    ):
        api_start = max(start_ms, end_ms - 86400000)
        items, more = self._paged_all(
            lambda next_key: self.get_sport_records_by_time(
                api_start, end_ms, next_key, limit, reverse
            ),
            "sport_records",
            start_ms,
            end_ms,
            max_pages,
            stop_below_start=True,
        )
        return {"sport_records": items, "has_more": more}
