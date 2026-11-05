import contextlib
import curses
import locale
import time
from dataclasses import dataclass
from os import PathLike

from .charsets import ASCII, Charset, supports_unicode
from .convert import DEFAULT_CELL_ASPECT, DEFAULT_EDGE_THRESHOLD, fit_size, image_to_cells
from .subtitles import Cue, format_time, lyrics_lines, parse_time
from .video import Video
from .viewer import _addstr, _color_attrs, _draw_row

SHORT_SEEK = 5.0
LONG_SEEK = 60.0
# Decode at the sub-cell resolution image_to_cells looks for contours at; anything
# bigger is thrown away by it anyway.
_DECODE_SCALE = 4
# Keep the clock on the status bar ticking even for slideshow-like videos.
_MAX_WAIT = 0.25
_QUIT_KEYS = {ord("q"), ord("Q"), 27}
_ENTER_KEYS = {"\n", "\r", curses.KEY_ENTER}
_BACKSPACE_KEYS = {"\b", "\x7f", curses.KEY_BACKSPACE}


@dataclass(frozen=True)
class _Glyphs:
    playing: str
    paused: str
    filled: str
    knob: str
    empty: str
    border: str
    keys: tuple[tuple[str, str], ...]


_UNICODE_GLYPHS = _Glyphs(
    playing="▶",
    paused="‖",
    filled="━",
    knob="●",
    empty="─",
    border="│",
    keys=(
        ("←/→", "5s"),
        ("↓/↑", "1m"),
        ("space", "pause"),
        ("j", "jump to"),
        ("s", "subtitles"),
        ("q", "quit"),
    ),
)
_ASCII_GLYPHS = _Glyphs(
    playing=">",
    paused="||",
    filled="=",
    knob="O",
    empty="-",
    border="|",
    keys=(
        ("left/right", "5s"),
        ("down/up", "1m"),
        ("space", "pause"),
        ("j", "jump to"),
        ("s", "subtitles"),
        ("q", "quit"),
    ),
)


def play_video(
    video: Video | str | PathLike,
    subtitles: list[Cue] | None = None,
    title: str = "",
    start: float = 0.0,
    charset: Charset = ASCII,
    colors: int = 16,
    color: bool = True,
    cell_aspect: float = DEFAULT_CELL_ASPECT,
    edge_threshold: float = DEFAULT_EDGE_THRESHOLD,
    dither: bool = False,
) -> None:
    """Play the video full screen until q or Esc, with the subtitles shown beside it."""
    if not isinstance(video, Video):
        with Video(video) as opened:
            play_video(
                opened,
                subtitles,
                title,
                start,
                charset,
                colors,
                color,
                cell_aspect,
                edge_threshold,
                dither,
            )
            return
    locale.setlocale(locale.LC_ALL, "")
    glyphs = _UNICODE_GLYPHS if supports_unicode() else _ASCII_GLYPHS
    render = {
        "charset": charset,
        "colors": colors,
        "edge_threshold": edge_threshold,
        "dither": dither,
    }
    curses.wrapper(
        lambda screen: _Player(
            screen, video, subtitles or [], title, glyphs, color, cell_aspect, render
        ).run(start)
    )


class _Clock:
    def __init__(self):
        self._base = 0.0
        self._since: float | None = None

    @property
    def playing(self) -> bool:
        return self._since is not None

    def now(self) -> float:
        if self._since is None:
            return self._base
        return self._base + time.monotonic() - self._since

    def play(self) -> None:
        if self._since is None:
            self._since = time.monotonic()

    def pause(self) -> None:
        self._base = self.now()
        self._since = None

    def set(self, position: float) -> None:
        self._base = position
        if self._since is not None:
            self._since = time.monotonic()


class _Player:
    def __init__(self, screen, video, cues, title, glyphs, color, cell_aspect, render):
        self.screen = screen
        self.video = video
        self.cues = cues
        self.title = title
        self.glyphs = glyphs
        self.cell_aspect = cell_aspect
        self.render = render
        self.show_subtitles = bool(cues)
        self.clock = _Clock()
        self.frames = iter(())
        self.pending = None
        self.shown = None
        self.ended = False
        self._cells_key = None
        self._cells = []

        with contextlib.suppress(curses.error):
            curses.curs_set(0)
        # Esc should quit right away rather than wait a second for an escape sequence.
        if hasattr(curses, "set_escdelay"):
            curses.set_escdelay(25)
        attrs = _color_attrs(render["colors"]) if color else {}
        self.colors = attrs
        self.bright = attrs.get(15, 0) | curses.A_BOLD
        self.dim = attrs[8] if 8 in attrs and curses.COLORS >= 16 else curses.A_DIM

    def run(self, start: float) -> None:
        self.clock.play()
        self.seek(start)
        while True:
            self.advance()
            self.draw()
            self.screen.timeout(self.wait_ms())
            key = self.screen.getch()
            if key in _QUIT_KEYS:
                return
            self.handle(key)

    def handle(self, key: int) -> None:
        if key == ord(" "):
            if self.ended:
                self.seek(0)
                self.clock.play()
            elif self.clock.playing:
                self.clock.pause()
            else:
                self.clock.play()
        elif key in (curses.KEY_LEFT, curses.KEY_RIGHT, curses.KEY_DOWN, curses.KEY_UP):
            step = SHORT_SEEK if key in (curses.KEY_LEFT, curses.KEY_RIGHT) else LONG_SEEK
            sign = 1 if key in (curses.KEY_RIGHT, curses.KEY_UP) else -1
            self.seek(self.clock.now() + sign * step)
        elif key in (ord("j"), ord("J")):
            target = self.ask_time()
            self.screen.touchwin()
            if target is not None:
                self.seek(target)
        elif key in (ord("s"), ord("S")) and self.cues:
            self.show_subtitles = not self.show_subtitles

    def seek(self, position: float) -> None:
        if self.video.duration:
            position = min(position, self.video.duration)
        position = max(position, 0.0)
        self.frames = self.video.frames(position)
        self.clock.set(position)
        self.ended = False
        # Show where we landed even while paused.
        self.pending = next(self.frames, None)
        if self.pending is not None:
            self.shown, self.pending = self.pending, next(self.frames, None)

    def advance(self) -> None:
        now = self.clock.now()
        # Frames we are already late for are decoded but never converted to text.
        while self.pending is not None and self.pending.time <= now:
            self.shown, self.pending = self.pending, next(self.frames, None)
        if self.pending is None and not self.ended:
            last = self.shown.time + 1 / self.video.fps if self.shown else 0.0
            if now >= last:
                self.ended = True
                self.clock.pause()
                self.clock.set(max(last, self.video.duration))

    def wait_ms(self) -> int:
        if not self.clock.playing:
            return -1
        wait = _MAX_WAIT
        if self.pending is not None:
            wait = min(wait, self.pending.time - self.clock.now())
        return max(int(wait * 1000), 0)

    def layout(self):
        height, width = self.screen.getmaxyx()
        bar_rows = 2 if height >= 6 else 1
        panel = 0
        if self.show_subtitles and width >= 50:
            panel = min(max(width // 3, 24), 60)
        video_width = width - panel - (1 if panel else 0)
        return width, height, bar_rows, video_width, panel

    def draw(self) -> None:
        width, height, bar_rows, video_width, panel = self.layout()
        self.screen.erase()
        video_height = height - bar_rows
        if video_height > 0 and video_width > 0:
            self.draw_frame(video_width, video_height)
            if panel:
                for y in range(video_height):
                    _addstr(self.screen, y, video_width, self.glyphs.border, self.dim)
                self.draw_subtitles(video_width + 1, panel, video_height)
        if height > 0 and width > 1:
            self.draw_progress(height - bar_rows, width)
            if bar_rows == 2:
                self.draw_keys(height - 1, width)
        self.screen.refresh()

    def draw_frame(self, width: int, height: int) -> None:
        if self.shown is None:
            return
        cols, rows = fit_size(self.video.width, self.video.height, width, height, self.cell_aspect)
        # Holding the frame itself, not its id, which a later frame could reuse.
        key = (self.shown, cols, rows)
        if key != self._cells_key:
            image = self.shown.to_image(cols * _DECODE_SCALE, rows * _DECODE_SCALE)
            self._cells = image_to_cells(image, cols, rows, **self.render)
            self._cells_key = key
        top = (height - rows) // 2
        left = (width - cols) // 2
        for y, row in enumerate(self._cells):
            _draw_row(self.screen, top + y, left, row, self.colors)

    def draw_subtitles(self, left: int, width: int, height: int) -> None:
        text_width = max(width - 2, 1)
        lines = lyrics_lines(self.cues, self.clock.now(), text_width, height)
        for y, (text, current) in enumerate(lines):
            if text:
                x = left + 1 + (text_width - len(text)) // 2
                _addstr(self.screen, y, x, text, self.bright if current else self.dim)

    def draw_progress(self, y: int, width: int) -> None:
        g = self.glyphs
        now, duration = self.clock.now(), self.video.duration
        icon = g.paused if not self.clock.playing or self.ended else g.playing
        left = f" {icon} {format_time(now)} "
        right = f" {format_time(duration)} "
        bar_width = width - len(left) - len(right) - 1
        _addstr(self.screen, y, 0, left, self.bright)
        if bar_width >= 3:
            fraction = min(now / duration, 1.0) if duration else 0.0
            knob = round(fraction * (bar_width - 1))
            _addstr(self.screen, y, len(left), g.filled * knob + g.knob, self.bright)
            _addstr(
                self.screen, y, len(left) + knob + 1, g.empty * (bar_width - knob - 1), self.dim
            )
            _addstr(self.screen, y, len(left) + bar_width, right, 0)

    def draw_keys(self, y: int, width: int) -> None:
        x = 1
        for key, label in self.glyphs.keys:
            if x + len(key) + len(label) + 2 >= width:
                return
            _addstr(self.screen, y, x, key, curses.A_REVERSE)
            _addstr(self.screen, y, x + len(key) + 1, label, 0)
            x += len(key) + len(label) + 3
        title = self.title[: width - x - 2]
        if title:
            _addstr(self.screen, y, width - len(title) - 1, title, self.dim)

    def ask_time(self) -> float | None:
        """Pause and read a time from a small dialog; None if cancelled."""
        was_playing = self.clock.playing
        self.clock.pause()
        try:
            return self._read_time()
        finally:
            with contextlib.suppress(curses.error):
                curses.curs_set(0)
            if was_playing:
                self.clock.play()

    def _read_time(self) -> float | None:
        height, width = self.screen.getmaxyx()
        box_height, box_width = 6, min(40, width)
        if height < box_height or box_width < 20:
            return None
        window = curses.newwin(box_height, box_width, (height - 6) // 2, (width - box_width) // 2)
        window.keypad(True)
        with contextlib.suppress(curses.error):
            curses.curs_set(1)
        text, message = "", f"0 - {format_time(self.video.duration)}"
        while True:
            window.erase()
            window.box()
            _addstr(window, 0, 2, " Jump to ", self.bright)
            _addstr(window, 1, 2, "h:mm:ss, m:ss or seconds", 0)
            _addstr(window, 3, 2, message[: box_width - 4], self.dim)
            _addstr(window, 4, 2, "Enter: go  Esc: cancel"[: box_width - 4], self.dim)
            _addstr(window, 2, 2, "> " + text, self.bright)
            window.move(2, min(4 + len(text), box_width - 2))
            window.refresh()
            key = window.get_wch()
            if key in _ENTER_KEYS:
                try:
                    return parse_time(text)
                except ValueError:
                    message = "not a time"
            elif key in ("\x1b", curses.KEY_RESIZE):
                return None
            elif key in _BACKSPACE_KEYS:
                text = text[:-1]
            elif isinstance(key, str) and key in "0123456789:.," and len(text) < box_width - 8:
                text += key
