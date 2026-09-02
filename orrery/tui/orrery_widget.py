"""A slowly turning line-art orrery: a gold sun and planets on concentric orbits.

Ambient, low frame rate, aspect-corrected so the orbits read as circles. Pure
rendering, no engine calls.
"""

from __future__ import annotations

import math

from rich.text import Text
from textual.widgets import Static

from .theme import GOLD, RING

# (radius fraction of max, angular speed, starting angle offset, planet glyph, color).
# Inner orbits turn faster, as a real orrery does; offsets spread the planets out.
_ORBITS = [
    (0.30, 1.00, 0.4, "*", "#ffd76a"),
    (0.48, 0.66, 2.1, "*", "#e8c15a"),
    (0.66, 0.45, 3.7, "o", "#c0c8e0"),
    (0.84, 0.31, 5.0, "*", "#9aa7d0"),
    (1.00, 0.21, 1.2, "o", "#f0e6c0"),
]
_ASPECT = 2.1  # terminal cells are ~2x taller than wide; widen x so circles look round


class OrreryWidget(Static):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._phase = 0.0

    def on_mount(self) -> None:
        self.update(self._frame())
        self.set_interval(0.12, self._tick)

    def _tick(self) -> None:
        self._phase += 0.05
        self.update(self._frame())

    def _frame(self) -> Text:
        w = max(self.size.width, 12)
        h = max(self.size.height, 8)
        cx, cy = w / 2, h / 2
        maxr = min(cx / _ASPECT, cy) - 1
        if maxr < 2:
            return Text("")
        grid: list[list[tuple[str, str | None]]] = [
            [(" ", None) for _ in range(w)] for _ in range(h)
        ]

        def put(x: float, y: float, ch: str, style: str | None) -> None:
            xi, yi = int(round(x)), int(round(y))
            if 0 <= xi < w and 0 <= yi < h:
                grid[yi][xi] = (ch, style)

        # faint orbit rings
        for rf, *_rest in _ORBITS:
            r = maxr * rf
            steps = max(24, int(2 * math.pi * r))
            for s in range(steps):
                a = 2 * math.pi * s / steps
                put(cx + math.cos(a) * r * _ASPECT, cy + math.sin(a) * r, "·", RING)

        # planets
        for rf, speed, offset, glyph, color in _ORBITS:
            r = maxr * rf
            a = self._phase * speed + offset
            put(cx + math.cos(a) * r * _ASPECT, cy + math.sin(a) * r, glyph, color)

        # sun
        put(cx, cy, "☉", GOLD)

        text = Text(no_wrap=True, overflow="crop")
        for row in grid:
            for ch, style in row:
                text.append(ch, style=style)
            text.append("\n")
        return text
