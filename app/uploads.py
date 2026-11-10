from __future__ import annotations

from uuid import uuid4

from .config import settings

IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/heic": ".heic",
    "image/heif": ".heif",
}


def save_image(content: bytes, content_type: str) -> str:
    extension = IMAGE_TYPES.get((content_type or "").lower())
    if extension is None:
        raise ValueError("unsupported image type")
    filename = f"{uuid4().hex}{extension}"
    settings.ensure_dirs()
    (settings.upload_dir / filename).write_bytes(content)
    return filename


def delete_image(photo_path: str | None) -> None:
    if not photo_path:
        return
    try:
        target = (settings.upload_dir / photo_path).resolve()
        if target.parent == settings.upload_dir.resolve() and target.is_file():
            target.unlink()
    except OSError:
        pass
