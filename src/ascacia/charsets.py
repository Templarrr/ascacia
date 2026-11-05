import bisect
import sys
from dataclasses import dataclass
from functools import cached_property
from typing import TextIO


@dataclass(frozen=True)
class Charset:
    """Symbols used to draw an image.

    ``ramp`` goes from the emptiest to the densest symbol. ``levels`` optionally gives
    each symbol's ink coverage from 0 to 1; without it the symbols are treated as evenly
    spaced. ``edges`` holds the horizontal, rising, vertical and falling line symbols;
    leave it empty to draw with the ramp only.
    """

    ramp: str
    edges: str = ""
    unicode: bool = False
    levels: tuple[float, ...] | None = None

    def __post_init__(self):
        if len(self.ramp) < 2:
            raise ValueError("ramp needs at least two symbols")
        if self.edges and len(self.edges) != 4:
            raise ValueError("edges must have exactly four symbols: - / | \\")
        if self.levels is not None and len(self.levels) != len(self.ramp):
            raise ValueError("levels must have one value per ramp symbol")
        if self.levels is not None and list(self.levels) != sorted(self.levels):
            raise ValueError("levels must go from the emptiest to the densest symbol")

    def symbol(self, brightness: float) -> str:
        """Symbol for a brightness from 0 to 255."""
        return self._lookup[min(max(round(brightness), 0), 255)]

    def coverage(self, brightness: float) -> float:
        """Ink coverage from 0 to 1 that best shows a brightness from 0 to 255."""
        if self.levels is None:
            return brightness / 255
        # Coverage mixes light linearly while brightness is gamma encoded, so compare
        # in linear light; this spreads the many sparse glyphs over the darker half.
        return (max(brightness, 0) / 255) ** 2.2

    def nearest(self, coverage: float) -> int:
        """Index of the ramp symbol whose coverage is closest to ``coverage``."""
        index = bisect.bisect(self._midpoints, coverage)
        return min(index, len(self.ramp) - 1)

    @cached_property
    def tones(self) -> tuple[float, ...]:
        """Coverage of each ramp symbol, in the same scale as :meth:`coverage`."""
        if self.levels is None:
            top = len(self.ramp) - 1
            return tuple(i / top for i in range(top + 1))
        return self.levels

    @cached_property
    def _midpoints(self) -> list[float]:
        return [(a + b) / 2 for a, b in zip(self.tones, self.tones[1:], strict=False)]

    @cached_property
    def _lookup(self) -> str:
        return "".join(self.ramp[self.nearest(self.coverage(value))] for value in range(256))


ASCII = Charset(ramp=" .:;+=*#%@", edges="-/|\\")
# Coverage measured by rendering each glyph in DejaVu Sans Mono, Liberation Mono and
# JetBrains Mono and averaging; real terminal fonts differ a little.
# fmt: off
UNICODE = Charset(
    ramp=" ·◦:°;•÷+×○≈∞±□≡o░#%&$⊞@◉●▒■▚▓█",
    levels=(
        0.0, 0.027, 0.035, 0.051, 0.058, 0.07, 0.081, 0.087, 0.098, 0.102, 0.112,
        0.119, 0.138, 0.142, 0.148, 0.154, 0.164, 0.187, 0.202, 0.209, 0.22, 0.232,
        0.251, 0.277, 0.291, 0.331, 0.416, 0.438, 0.506, 0.767, 1.0,
    ),
    edges="─╱│╲",
    unicode=True,
)
# fmt: on

CHARSETS = {"ascii": ASCII, "unicode": UNICODE}


def supports_unicode(stream: TextIO | None = None) -> bool:
    encoding = getattr(stream or sys.stdout, "encoding", None) or ""
    return encoding.lower().replace("-", "") in {"utf8", "utf16", "utf32"}
