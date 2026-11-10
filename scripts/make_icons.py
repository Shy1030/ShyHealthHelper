"""生成 PWA 图标（纯 Python，无需 Pillow）。"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "web" / "icons"

START = (207, 87, 117)
END = (95, 58, 92)
STARS = ((0.705, 0.660, 0.024), (0.300, 0.715, 0.017), (0.725, 0.310, 0.014))


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _sample(x: float, y: float) -> tuple[int, int, int, int]:
    t = max(0.0, min(1.0, y))
    color = _mix(START, END, t)

    dx = x - 0.5
    dy = y - 0.46
    if dx * dx + dy * dy <= 0.04:
        color = (255, 252, 250)

    hx = x - 0.585
    hy = y - 0.415
    if hx * hx + hy * hy <= 0.0529:
        glow = 1 - (hx * hx + hy * hy) / 0.0529
        color = _mix(color, (255, 255, 255), 0.10 + glow * 0.12)

    glow = max(0.0, 1 - ((x - 0.7) ** 2 + (y - 0.15) ** 2) / 0.12)
    if glow > 0:
        color = _mix(color, (255, 255, 255), glow * 0.16)

    for sx, sy, radius in STARS:
        if (x - sx) ** 2 + (y - sy) ** 2 <= radius * radius:
            color = (255, 246, 240)

    return color[0], color[1], color[2], 255


def make_png(size: int, path: Path, supersample: int = 2) -> None:
    rows: list[bytes] = []
    for py in range(size):
        row = bytearray([0])
        for px in range(size):
            r = g = b = a = 0
            for sy in range(supersample):
                for sx in range(supersample):
                    sample = _sample(
                        (px + (sx + 0.5) / supersample) / size,
                        (py + (sy + 0.5) / supersample) / size,
                    )
                    r += sample[0]
                    g += sample[1]
                    b += sample[2]
                    a += sample[3]
            count = supersample * supersample
            row += bytes((r // count, g // count, b // count, a // count))
        rows.append(bytes(row))

    raw = b"".join(rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        payload = kind + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = (
        signature
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)
    print(f"wrote {path} ({size}x{size})")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for size in (180, 192, 512):
        make_png(size, OUT_DIR / f"icon-{size}.png")


if __name__ == "__main__":
    main()
