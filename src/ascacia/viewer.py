import contextlib
import curses
import locale

from PIL import Image

from .charsets import ASCII, Charset
from .convert import (
    DEFAULT_CELL_ASPECT,
    DEFAULT_EDGE_THRESHOLD,
    fit_size,
    image_to_cells,
)

_QUIT_KEYS = {ord("q"), ord("Q"), 27}


def view_image(
    image: Image.Image,
    title: str = "",
    charset: Charset = ASCII,
    colors: int = 16,
    color: bool = True,
    cell_aspect: float = DEFAULT_CELL_ASPECT,
    edge_threshold: float = DEFAULT_EDGE_THRESHOLD,
) -> None:
    """Show the image full screen until q or Esc is pressed, refitting on terminal resize."""
    # Without this curses mangles multibyte symbols.
    locale.setlocale(locale.LC_ALL, "")
    curses.wrapper(_run, image, title, charset, colors, color, cell_aspect, edge_threshold)


def _run(screen, image, title, charset, colors, color, cell_aspect, edge_threshold):
    curses.curs_set(0)
    attrs = _color_attrs(colors) if color else {}
    while True:
        screen.erase()
        height, width = screen.getmaxyx()
        # The bottom line is kept for the status bar.
        if height > 1 and width > 0:
            cols, rows = fit_size(image.width, image.height, width, height - 1, cell_aspect)
            cells = image_to_cells(image, cols, rows, charset, colors, edge_threshold)
            top = (height - 1 - rows) // 2
            left = (width - cols) // 2
            for y, row in enumerate(cells):
                _draw_row(screen, top + y, left, row, attrs)
            status = f" {title}  {image.width}x{image.height} -> {cols}x{rows}  q: quit"
            _addstr(screen, height - 1, 0, status[: width - 1], curses.A_REVERSE)
        screen.refresh()
        if screen.getch() in _QUIT_KEYS:
            return


def _draw_row(screen, y, x, row, attrs):
    # Writing runs of the same color is much faster than one call per cell.
    start = 0
    for end in range(1, len(row) + 1):
        if end == len(row) or row[end].color != row[start].color:
            text = "".join(cell.char for cell in row[start:end])
            _addstr(screen, y, x + start, text, attrs.get(row[start].color, 0))
            start = end


def _addstr(screen, y, x, text, attr):
    # curses raises after writing the bottom-right cell even though the text is drawn.
    with contextlib.suppress(curses.error):
        screen.addstr(y, x, text, attr)


def _color_attrs(colors: int) -> dict[int, int]:
    if not curses.has_colors():
        return {}
    curses.start_color()
    try:
        curses.use_default_colors()
        background = -1
    except curses.error:
        background = curses.COLOR_BLACK
    attrs = {}
    for index in range(1, colors):
        if index < curses.COLORS:
            curses.init_pair(index, index, background)
            attrs[index] = curses.color_pair(index)
        else:
            # 8-color terminals show the bright half as bold.
            curses.init_pair(index, index - 8, background)
            attrs[index] = curses.color_pair(index) | curses.A_BOLD
    return attrs
