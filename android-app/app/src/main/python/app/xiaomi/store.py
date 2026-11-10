"""小米账号凭据的本地存储。

桌面/服务器版优先使用 Fernet 加密。Chaquopy 试验版没有打包 cryptography 时，
会退化为简单的 XOR 混淆，仅用于原型验证，不能作为生产安全方案。
"""

from __future__ import annotations

import json
import os
import threading

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # Chaquopy 试验版可能没有 cryptography
    Fernet = None

    class InvalidToken(Exception):
        pass


from ..config import settings

_LOCK = threading.Lock()
_FALLBACK_MAGIC = b"MCX1"


class XiaomiStore:
    def __init__(self) -> None:
        self.key_path = settings.data_dir / "xiaomi.key"
        self.store_path = settings.data_dir / "xiaomi_credentials.enc"

    def _key(self) -> bytes:
        settings.ensure_dirs()
        if self.key_path.exists():
            return self.key_path.read_bytes().strip()
        key = Fernet.generate_key() if Fernet else os.urandom(32)
        self.key_path.write_bytes(key)
        self._chmod(self.key_path)
        return key

    @staticmethod
    def _chmod(path) -> None:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def _xor(self, data: bytes) -> bytes:
        key = self._key()
        return bytes(byte ^ key[index % len(key)] for index, byte in enumerate(data))

    def load(self) -> dict:
        with _LOCK:
            try:
                token = self.store_path.read_bytes()
                if not token:
                    return {}
                if token.startswith(_FALLBACK_MAGIC):
                    plain = self._xor(token[len(_FALLBACK_MAGIC) :])
                elif Fernet:
                    plain = Fernet(self._key()).decrypt(token)
                else:
                    return {}
                data = json.loads(plain.decode("utf-8"))
                return data if isinstance(data, dict) else {}
            except (OSError, ValueError, InvalidToken, json.JSONDecodeError):
                return {}

    def save(self, data: dict) -> None:
        with _LOCK:
            settings.ensure_dirs()
            raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
            if Fernet:
                token = Fernet(self._key()).encrypt(raw)
            else:
                token = _FALLBACK_MAGIC + self._xor(raw)
            self.store_path.write_bytes(token)
            self._chmod(self.store_path)

    def clear(self) -> None:
        with _LOCK:
            for path in (self.store_path,):
                try:
                    path.unlink()
                except OSError:
                    pass


store = XiaomiStore()
