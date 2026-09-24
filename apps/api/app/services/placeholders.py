"""Neutral generated placeholder photos (no third-party images) for seed data and simulations."""

from __future__ import annotations

import hashlib
import io
import random

from PIL import Image, ImageDraw, ImageFilter

from app.domain.enums import SignalCategory

# Muted earth palettes per category: (sky, ground, accent)
PALETTES: dict[SignalCategory, tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]] = {
    SignalCategory.DUMP: ((196, 208, 219), (142, 124, 98), (92, 88, 84)),
    SignalCategory.ABANDONED: ((205, 214, 222), (176, 160, 112), (132, 140, 88)),
    SignalCategory.SELF_SEIZURE: ((190, 205, 220), (150, 140, 110), (120, 110, 104)),
    SignalCategory.OTHER: ((200, 210, 220), (150, 150, 130), (110, 120, 110)),
}


def placeholder_photo(seed: str, category: SignalCategory = SignalCategory.OTHER, size: int = 960) -> bytes:
    """Abstract landscape-like JPEG: sky, ground, horizon and a few blobs."""
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:12], 16))
    sky, ground, accent = PALETTES[category]
    width, height = size, int(size * 0.75)
    image = Image.new("RGB", (width, height), sky)
    draw = ImageDraw.Draw(image)
    horizon = int(height * rng.uniform(0.35, 0.5))
    draw.rectangle([0, horizon, width, height], fill=ground)
    # distant hills
    points = [(0, horizon)]
    for x in range(0, width + 60, 60):
        points.append((x, horizon - rng.randint(5, 40)))
    points.append((width, horizon))
    draw.polygon(points, fill=tuple(max(c - 25, 0) for c in ground))
    # objects
    for _ in range(rng.randint(5, 12)):
        cx, cy = rng.randint(0, width), rng.randint(horizon + 20, height)
        r = rng.randint(12, 60)
        shade = tuple(min(255, max(0, c + rng.randint(-30, 30))) for c in accent)
        draw.ellipse([cx - r, cy - r // 2, cx + r, cy + r // 2], fill=shade)
    image = image.filter(ImageFilter.GaussianBlur(1.2))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=82)
    return buffer.getvalue()
