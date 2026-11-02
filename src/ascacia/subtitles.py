import re
import textwrap
from dataclasses import dataclass
from os import PathLike
from pathlib import Path

SUBTITLE_SUFFIXES = (".srt", ".vtt")

_TIMING = re.compile(
    r"(?P<start>(?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*(?P<end>(?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})"
)
# HTML-like styling (<i>, <font ...>, <c.yellow>) and SSA overrides ({\an8}) that
# subtitle files often carry; the panel shows plain text.
_MARKUP = re.compile(r"<[^>]*>|\{\\[^}]*\}")


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def parse_subtitles(text: str) -> list[Cue]:
    """Parse SubRip (.srt) or WebVTT (.vtt) text into cues sorted by start time."""
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n")):
        lines = block.strip("\n").split("\n")
        for i, line in enumerate(lines):
            match = _TIMING.search(line)
            if match:
                body = "\n".join(_MARKUP.sub("", part).strip() for part in lines[i + 1 :])
                start, end = parse_time(match["start"]), parse_time(match["end"])
                if body.strip():
                    cues.append(Cue(start, end, body.strip()))
                break
    return sorted(cues, key=lambda cue: cue.start)


def load_subtitles(path: str | PathLike) -> list[Cue]:
    data = Path(path).read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Older .srt files are usually in a legacy 8-bit encoding; this never fails.
        text = data.decode("cp1252", errors="replace")
    return parse_subtitles(text)


def find_subtitles(video_path: str | PathLike) -> Path | None:
    """Subtitle file next to the video: ``movie.srt``, or ``movie.<lang>.srt`` and the like."""
    video_path = Path(video_path)
    candidates = [
        path
        for path in video_path.parent.glob(f"{_glob_escape(video_path.stem)}.*")
        if path.suffix.lower() in SUBTITLE_SUFFIXES and path.is_file()
    ]
    # Prefer the exact name, then the shortest (movie.en.srt over movie.en.forced.srt).
    candidates.sort(key=lambda path: (path.stem != video_path.stem, len(path.name), path.name))
    return candidates[0] if candidates else None


def _glob_escape(name: str) -> str:
    return re.sub(r"([*?\[])", r"[\1]", name)


def active_cues(cues: list[Cue], time: float) -> list[int]:
    return [i for i, cue in enumerate(cues) if cue.start <= time < cue.end]


def lyrics_lines(cues: list[Cue], time: float, width: int, height: int) -> list[tuple[str, bool]]:
    """Lay out the cues like song lyrics: ``height`` lines of ``(text, is_current)``.

    The current cue sits a third of the way down so more of what follows stays visible;
    between cues the next one takes its place, not highlighted.
    """
    if not cues or width <= 0 or height <= 0:
        return [("", False)] * max(height, 0)
    current = set(active_cues(cues, time))
    anchor = min(current) if current else _next_cue(cues, time)

    lines: list[tuple[str, bool]] = []
    anchor_line = 0
    for i, cue in enumerate(cues):
        if i == anchor:
            anchor_line = len(lines)
        for paragraph in cue.text.split("\n"):
            for line in textwrap.wrap(paragraph, width) or [""]:
                lines.append((line, i in current))
        lines.append(("", False))

    top = anchor_line - height // 3
    window = lines[max(top, 0) : top + height]
    padding = [("", False)] * max(-top, 0)
    window = padding + window
    return window + [("", False)] * (height - len(window))


def _next_cue(cues: list[Cue], time: float) -> int:
    for i, cue in enumerate(cues):
        if cue.start > time:
            return i
    return len(cues) - 1


def parse_time(text: str) -> float:
    """Seconds from ``1:02:03.5``, ``2:03``, ``123`` or the subtitle form ``00:02:03,500``."""
    parts = text.strip().replace(",", ".").split(":")
    if not 1 <= len(parts) <= 3 or not all(re.fullmatch(r"\d+(\.\d*)?", p) for p in parts):
        raise ValueError(f"not a time: {text!r}")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


def format_time(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"
