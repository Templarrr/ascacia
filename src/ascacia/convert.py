import math
from array import array
from dataclasses import dataclass
from os import PathLike

from PIL import Image, ImageDraw, ImageFilter, ImageMath, ImageOps

from .charsets import ASCII, Charset
from .colors import ANSI_RESET, ansi_sequence, nearest_color

# Terminal cells are roughly twice as tall as they are wide.
DEFAULT_CELL_ASPECT = 2.0
DEFAULT_EDGE_THRESHOLD = 0.12

# Gradients are measured on a grid this many pixels per cell side, which is
# enough to tell line directions apart without slowing large images down.
_SUBCELL = 4
_SOBEL_X = (-1, 0, 1, -2, 0, 2, -1, 0, 1)
# Laid out bottom row first because of how Pillow orients kernels: +y points down the image.
_SOBEL_Y = (1, 2, 1, 0, 0, 0, -1, -2, -1)
# Kernel output is clamped to 0..255, so the signed gradient is scaled and shifted to fit.
_SOBEL_SCALE = 8
_SOBEL_OFFSET = 128
_MIN_COHERENCE = 0.5


@dataclass(frozen=True)
class Cell:
    char: str
    color: int


def load_image(path: str | PathLike) -> Image.Image:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
            background = Image.new("RGBA", image.size, (0, 0, 0, 255))
            return Image.alpha_composite(background, image.convert("RGBA")).convert("RGB")
        return image.convert("RGB")


def fit_size(
    width: int,
    height: int,
    max_cols: int,
    max_rows: int,
    cell_aspect: float = DEFAULT_CELL_ASPECT,
) -> tuple[int, int]:
    """Largest (cols, rows) that fits the limits and keeps the image proportions on screen."""
    if width <= 0 or height <= 0:
        raise ValueError("image size must be positive")
    if max_cols <= 0 or max_rows <= 0:
        raise ValueError("terminal size must be positive")
    cols = max_cols
    rows = round(cols * height / (width * cell_aspect))
    if rows > max_rows:
        rows = max_rows
        cols = min(max_cols, round(rows * cell_aspect * width / height))
    return max(cols, 1), max(rows, 1)


def image_to_cells(
    image: Image.Image,
    cols: int,
    rows: int,
    charset: Charset = ASCII,
    colors: int = 16,
    edge_threshold: float = DEFAULT_EDGE_THRESHOLD,
) -> list[list[Cell]]:
    """Convert an image into a ``rows`` x ``cols`` grid of colored symbols.

    The image is stretched to the grid, use :func:`fit_size` first to keep its proportions.
    """
    if cols <= 0 or rows <= 0:
        raise ValueError("cols and rows must be positive")
    rgb = image.convert("RGB")
    data = rgb.resize((cols, rows), Image.Resampling.BOX).tobytes()
    averages = [tuple(data[i : i + 3]) for i in range(0, len(data), 3)]
    edges = _edge_symbols(rgb, cols, rows, charset.edges, edge_threshold)

    cells = []
    for i, rgb_average in enumerate(averages):
        edge = edges[i]
        if edge:
            symbol, neighbours = edge
            # The contour may sit in the dark cell next to an object; paint it in the
            # object's color rather than in the background's.
            source = max([rgb_average] + [averages[j] for j in neighbours], key=_brightness)
            cells.append(Cell(symbol, nearest_color(source, colors)))
        else:
            symbol = charset.symbol(_brightness(rgb_average))
            cells.append(Cell(symbol, nearest_color(rgb_average, colors)))
    return [cells[y * cols : (y + 1) * cols] for y in range(rows)]


def image_to_text(
    image: Image.Image,
    max_cols: int,
    max_rows: int,
    charset: Charset = ASCII,
    colors: int = 16,
    color: bool = True,
    cell_aspect: float = DEFAULT_CELL_ASPECT,
    edge_threshold: float = DEFAULT_EDGE_THRESHOLD,
) -> str:
    cols, rows = fit_size(image.width, image.height, max_cols, max_rows, cell_aspect)
    cells = image_to_cells(image, cols, rows, charset, colors, edge_threshold)
    return render_ansi(cells) if color else render_plain(cells)


def render_plain(cells: list[list[Cell]]) -> str:
    return "\n".join("".join(cell.char for cell in row) for row in cells)


def render_ansi(cells: list[list[Cell]]) -> str:
    lines = []
    for row in cells:
        parts = []
        current = None
        for cell in row:
            if cell.color != current:
                parts.append(ansi_sequence(cell.color))
                current = cell.color
            parts.append(cell.char)
        parts.append(ANSI_RESET)
        lines.append("".join(parts))
    return "\n".join(lines)


def _brightness(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    # Pure luminance would draw saturated blue and red almost empty, even though their
    # colored symbols show up clearly; blending in the HSV value keeps them visible.
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (luminance + max(r, g, b)) / 2


def _edge_symbols(
    image: Image.Image, cols: int, rows: int, symbols: str, threshold: float
) -> list[tuple[str, list[int]] | None]:
    """Line symbol and the cells on both sides of it for every cell crossed by a clear contour.

    Uses the per-cell structure tensor of the Sobel gradient: it gives the dominant
    direction even for thin lines, where plain gradient averaging cancels out.
    """
    if not symbols:
        return [None] * (cols * rows)

    gray = image.convert("L").resize((cols * _SUBCELL, rows * _SUBCELL), Image.Resampling.BOX)
    gx = _sobel(gray, _SOBEL_X)
    gy = _sobel(gray, _SOBEL_Y)

    def cell_mean(expression):
        product = ImageMath.lambda_eval(expression, x=gx, y=gy)
        return array("f", product.resize((cols, rows), Image.Resampling.BOX).tobytes())

    jxx = cell_mean(lambda a: (a["x"] - _SOBEL_OFFSET) * (a["x"] - _SOBEL_OFFSET))
    jyy = cell_mean(lambda a: (a["y"] - _SOBEL_OFFSET) * (a["y"] - _SOBEL_OFFSET))
    jxy = cell_mean(lambda a: (a["x"] - _SOBEL_OFFSET) * (a["y"] - _SOBEL_OFFSET))

    max_gradient = 4 * 255 / _SOBEL_SCALE
    energies = [xx + yy for xx, yy in zip(jxx, jyy, strict=True)]
    result: list[tuple[str, list[int]] | None] = [None] * (cols * rows)
    for i, energy in enumerate(energies):
        if energy <= 0 or math.sqrt(energy) / max_gradient < threshold:
            continue
        if math.hypot(jxx[i] - jyy[i], 2 * jxy[i]) / energy < _MIN_COHERENCE:
            continue
        gradient_angle = math.degrees(math.atan2(2 * jxy[i], jxx[i] - jyy[i])) / 2
        # A soft contour spreads over neighbouring cells; keep only its strongest cell
        # so lines come out one symbol thick.
        dx = round(math.cos(math.radians(gradient_angle)))
        dy = round(math.sin(math.radians(gradient_angle)))
        y, x = divmod(i, cols)
        neighbours = [
            i + sy * cols + sx
            for sx, sy in ((dx, dy), (-dx, -dy))
            if 0 <= x + sx < cols and 0 <= y + sy < rows
        ]
        if any(energies[j] > energy for j in neighbours):
            continue
        # The line runs across the gradient; flip the sign because image rows grow downwards.
        line_angle = (90 - gradient_angle) % 180
        result[i] = (symbols[round(line_angle / 45) % 4], neighbours)
    return result


def _sobel(gray: Image.Image, kernel: tuple[int, ...]) -> Image.Image:
    kernel_filter = ImageFilter.Kernel((3, 3), kernel, _SOBEL_SCALE, _SOBEL_OFFSET)
    filtered = gray.filter(kernel_filter).convert("F")
    # Pillow leaves the outermost pixels unfiltered; reset them to "no gradient".
    ImageDraw.Draw(filtered).rectangle(
        (0, 0, filtered.width - 1, filtered.height - 1), outline=_SOBEL_OFFSET
    )
    return filtered
