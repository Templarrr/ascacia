# ASCacia

Turn images (and, soon, videos) into colored ASCII or Unicode art and view them right in the
terminal, locally or over SSH.

## Install

```sh
uv tool install git+https://github.com/Templarrr/ascacia
```

## Usage

```sh
ascacia_image photo.jpg                     # full-screen viewer, q or Esc to quit
ascacia_image photo.jpg --charset unicode   # block and box-drawing symbols
ascacia_image photo.jpg --print --cols 100  # write the art to stdout instead
ascacia_image --help
```

The picture is fitted to the terminal keeping its proportions and is refitted when the
window is resized. Contours are drawn with line symbols (`- / | \` or `─ ╱ │ ╲`), the rest
with a density ramp, colored with the standard 16 (or 8) terminal colors.

`ascacia_video` is a placeholder for now.

## As a library

```python
from ascacia import UNICODE, fit_size, image_to_cells, load_image, render_ansi

image = load_image("photo.jpg")
cols, rows = fit_size(image.width, image.height, max_cols=120, max_rows=40)
cells = image_to_cells(image, cols, rows, charset=UNICODE)  # rows of Cell(char, color)
print(render_ansi(cells))
```

## Development

```sh
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```
