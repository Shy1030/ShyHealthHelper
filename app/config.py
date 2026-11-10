from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env_path(name: str, default: Path) -> Path:
    value = os.getenv(name, "").strip()
    return Path(value) if value else default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


class Settings:
    def __init__(self) -> None:
        self.base_dir = BASE_DIR
        self.web_dir = _env_path("APP_WEB_DIR", BASE_DIR / "web")
        self.data_dir = _env_path("APP_DATA_DIR", BASE_DIR / "data")
        self.db_path = _env_path("APP_DB_PATH", self.data_dir / "app.db")
        self.upload_dir = self.data_dir / "uploads"
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.deepseek_base_url = os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        ).rstrip("/")
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
        self.deepseek_vision_model = os.getenv(
            "DEEPSEEK_VISION_MODEL", "deepseek-flash"
        )
        self.timeout = _env_float("DEEPSEEK_TIMEOUT", 60.0)
        self._force_mock = os.getenv("AI_MOCK", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.mock_mode = self._force_mock or not self.deepseek_api_key
        self.max_upload_bytes = int(_env_float("MAX_UPLOAD_MB", 8.0) * 1024 * 1024)

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def apply_ai_settings(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        vision_model: str | None = None,
    ) -> None:
        if api_key is not None:
            self.deepseek_api_key = api_key.strip()
        if base_url:
            self.deepseek_base_url = base_url.strip().rstrip("/")
        if model:
            self.deepseek_model = model.strip()
        if vision_model:
            self.deepseek_vision_model = vision_model.strip()
        self.mock_mode = self._force_mock or not self.deepseek_api_key

    def reset_ai_settings(self) -> None:
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.deepseek_base_url = os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        ).rstrip("/")
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
        self.deepseek_vision_model = os.getenv(
            "DEEPSEEK_VISION_MODEL", "deepseek-flash"
        )
        self.mock_mode = self._force_mock or not self.deepseek_api_key

    @property
    def ai_mode(self) -> str:
        return "mock" if self.mock_mode else "deepseek"


settings = Settings()
