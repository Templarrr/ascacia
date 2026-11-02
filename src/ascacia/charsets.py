import sys
from dataclasses import dataclass
from typing import TextIO


@dataclass(frozen=True)
class Charset:
    """Symbols used to draw an image.

    ``ramp`` goes from the emptiest to the densest symbol. ``edges`` holds the
    horizontal, rising, vertical and falling line symbols; leave it empty to
    draw with the ramp only.
    """

    ramp: str
    edges: str = ""
    unicode: bool = False

    def __post_init__(self):
        if len(self.ramp) < 2:
            raise ValueError("ramp needs at least two symbols")
        if self.edges and len(self.edges) != 4:
            raise ValueError("edges must have exactly four symbols: - / | \\")


ASCII = Charset(ramp=" .:;+=*#%@", edges="-/|\\")
UNICODE = Charset(ramp=" ·:░▒▓█", edges="─╱│╲", unicode=True)

CHARSETS = {"ascii": ASCII, "unicode": UNICODE}


def supports_unicode(stream: TextIO | None = None) -> bool:
    encoding = getattr(stream or sys.stdout, "encoding", None) or ""
    return encoding.lower().replace("-", "") in {"utf8", "utf16", "utf32"}
