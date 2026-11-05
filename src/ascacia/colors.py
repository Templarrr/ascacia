import colorsys
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from .dither import diffuse


@dataclass(frozen=True)
class TerminalColor:
    index: int
    name: str
    rgb: tuple[int, int, int]


# xterm defaults; the real shades depend on the user's terminal theme.
ANSI_COLORS = (
    TerminalColor(0, "black", (0, 0, 0)),
    TerminalColor(1, "red", (205, 0, 0)),
    TerminalColor(2, "green", (0, 205, 0)),
    TerminalColor(3, "yellow", (205, 205, 0)),
    TerminalColor(4, "blue", (0, 0, 238)),
    TerminalColor(5, "magenta", (205, 0, 205)),
    TerminalColor(6, "cyan", (0, 205, 205)),
    TerminalColor(7, "white", (229, 229, 229)),
    TerminalColor(8, "bright_black", (127, 127, 127)),
    TerminalColor(9, "bright_red", (255, 0, 0)),
    TerminalColor(10, "bright_green", (0, 255, 0)),
    TerminalColor(11, "bright_yellow", (255, 255, 0)),
    TerminalColor(12, "bright_blue", (92, 92, 255)),
    TerminalColor(13, "bright_magenta", (255, 0, 255)),
    TerminalColor(14, "bright_cyan", (0, 255, 255)),
    TerminalColor(15, "bright_white", (255, 255, 255)),
)

# Pure hues to match against after normalizing brightness away.
_HUES = {
    1: (255, 0, 0),
    2: (0, 255, 0),
    3: (255, 255, 0),
    4: (0, 0, 255),
    5: (255, 0, 255),
    6: (0, 255, 255),
    7: (255, 255, 255),
}
_BRIGHT_VALUE = 170
# Palette hues in color wheel order, one HSV sector apart.
_WHEEL = (1, 3, 2, 6, 4, 5)
_MIN_SATURATION = 0.1


# Video calls this for every cell of every frame, and neighbouring cells and frames
# repeat colors a lot.
@lru_cache(maxsize=1 << 16)
def nearest_color(rgb: tuple[int, int, int], colors: int = 16) -> int:
    """Return the ANSI color index (1-15) that best matches the hue of ``rgb``.

    Brightness is mostly conveyed by symbol density, so the color only carries
    the hue. Black is never returned because it would be invisible on a dark
    background.
    """
    _check_colors(colors)
    return _shade(_nearest_hue(_full_brightness(rgb)), max(rgb), colors)


def dither_colors(pixels: Sequence[tuple[int, int, int]], cols: int, colors: int = 16) -> list[int]:
    """:func:`nearest_color` for a row-major grid of pixels, with the rounding error diffused.

    Neighbouring cells then mix the few terminal colors so that they average out to the
    real one: red and yellow for orange, magenta and white for pink.
    """
    _check_colors(colors)
    hsv = [colorsys.rgb_to_hsv(*(channel / 255 for channel in rgb)) for rgb in pixels]

    def quantize(i, wanted):
        # Hue and saturation are dithered apart so that a cell only ever takes one of the
        # two palette hues around its own, or white; mixing in all of RGB at once also
        # throws in hues from across the wheel, e.g. magenta specks in brown.
        hue, saturation = wanted
        _, own_saturation, value = hsv[i]
        sector = round(hue)
        saturation = min(max(saturation, 0.0), 1.0)
        # A gray cell has no hue of its own to show.
        colored = saturation >= 0.5 and own_saturation >= _MIN_SATURATION
        index = _WHEEL[sector % 6] if colored else 7
        # The symbol already shows the brightness, so a dim cell's color barely counts.
        return index, ((hue - sector) * own_saturation * value, (saturation - colored) * value)

    indices = diffuse([(hue * 6, saturation) for hue, saturation, _ in hsv], cols, quantize)
    return [_shade(index, max(rgb), colors) for index, rgb in zip(indices, pixels, strict=True)]


def _check_colors(colors: int) -> None:
    if colors not in (8, 16):
        raise ValueError("colors must be 8 or 16")


def _full_brightness(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    value = max(rgb)
    if value == 0:
        return (255.0, 255.0, 255.0)
    scale = 255 / value
    r, g, b = rgb
    return (r * scale, g * scale, b * scale)


def _nearest_hue(rgb: Sequence[float]) -> int:
    r, g, b = rgb
    return min(
        _HUES,
        key=lambda i: (r - _HUES[i][0]) ** 2 + (g - _HUES[i][1]) ** 2 + (b - _HUES[i][2]) ** 2,
    )


def _shade(hue: int, value: int, colors: int) -> int:
    if colors == 16 and value >= _BRIGHT_VALUE:
        return hue + 8
    return hue


def ansi_sequence(index: int) -> str:
    code = 30 + index if index < 8 else 90 + index - 8
    return f"\x1b[{code}m"


ANSI_RESET = "\x1b[0m"
