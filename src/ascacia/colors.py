from dataclasses import dataclass
from functools import lru_cache


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


# Video calls this for every cell of every frame, and neighbouring cells and frames
# repeat colors a lot.
@lru_cache(maxsize=1 << 16)
def nearest_color(rgb: tuple[int, int, int], colors: int = 16) -> int:
    """Return the ANSI color index (1-15) that best matches the hue of ``rgb``.

    Brightness is mostly conveyed by symbol density, so the color only carries
    the hue. Black is never returned because it would be invisible on a dark
    background.
    """
    if colors not in (8, 16):
        raise ValueError("colors must be 8 or 16")
    value = max(rgb)
    if value == 0:
        return 7
    scale = 255 / value
    r, g, b = (channel * scale for channel in rgb)
    hue = min(
        _HUES,
        key=lambda i: (r - _HUES[i][0]) ** 2 + (g - _HUES[i][1]) ** 2 + (b - _HUES[i][2]) ** 2,
    )
    if colors == 16 and value >= _BRIGHT_VALUE:
        return hue + 8
    return hue


def ansi_sequence(index: int) -> str:
    code = 30 + index if index < 8 else 90 + index - 8
    return f"\x1b[{code}m"


ANSI_RESET = "\x1b[0m"
