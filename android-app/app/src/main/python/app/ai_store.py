"""本地 DeepSeek AI 设置持久化（手机端使用）。"""

from __future__ import annotations

import json
import os
import threading

from .config import settings

_LOCK = threading.RLock()
_FILE_NAME = "ai_settings.json"


def _path():
    return settings.data_dir / _FILE_NAME


def load_settings() -> dict:
    with _LOCK:
        try:
            data = json.loads(_path().read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, json.JSONDecodeError):
            return {}


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * max(4, len(key) - 8) + key[-4:]


def public_settings() -> dict:
    data = load_settings()
    key = str(data.get("api_key") or "")
    return {
        "configured": bool(key),
        "api_key_masked": mask_key(key),
        "base_url": data.get("base_url") or settings.deepseek_base_url,
        "model": data.get("model") or settings.deepseek_model,
        "vision_model": data.get("vision_model") or settings.deepseek_vision_model,
        "ai_mode": settings.ai_mode,
        "mock_mode": settings.mock_mode,
    }


def apply_saved_ai_settings() -> None:
    data = load_settings()
    if not data:
        return
    settings.apply_ai_settings(
        api_key=str(data.get("api_key") or ""),
        base_url=data.get("base_url"),
        model=data.get("model"),
        vision_model=data.get("vision_model"),
    )


def save_ai_settings(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    vision_model: str | None = None,
) -> dict:
    with _LOCK:
        data = load_settings()
        if api_key is not None:
            data["api_key"] = api_key.strip()
        if base_url:
            data["base_url"] = base_url.strip().rstrip("/")
        if model:
            data["model"] = model.strip()
        if vision_model:
            data["vision_model"] = vision_model.strip()
        settings.ensure_dirs()
        path = _path()
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    settings.apply_ai_settings(
        api_key=data.get("api_key", ""),
        base_url=data.get("base_url"),
        model=data.get("model"),
        vision_model=data.get("vision_model"),
    )
    return public_settings()


def clear_ai_settings() -> dict:
    with _LOCK:
        try:
            _path().unlink()
        except OSError:
            pass
    settings.reset_ai_settings()
    return public_settings()
