import pytest
from PIL import Image, ImageDraw

from ascacia import (
    ASCII,
    UNICODE,
    Charset,
    fit_size,
    image_to_cells,
    image_to_text,
    load_image,
    render_ansi,
    render_plain,
)


def line_image(start, end, size=(200, 100)):
    image = Image.new("RGB", size)
    ImageDraw.Draw(image).line((*start, *end), fill="white", width=4)
    return image


def chars(cells):
    return {cell.char for row in cells for cell in row}


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        (400, 100, (80, 10)),  # wide image is limited by columns
        (100, 400, (12, 24)),  # tall image is limited by rows
        (100, 50, (80, 20)),  # square on screen: 80 cols x 20 rows of 2:1 cells
    ],
)
def test_fit_size_keeps_proportions_within_limits(width, height, expected):
    assert fit_size(width, height, 80, 24) == expected


def test_fit_size_rejects_empty_terminal():
    with pytest.raises(ValueError):
        fit_size(100, 100, 0, 24)


def test_grid_has_requested_size():
    cells = image_to_cells(Image.new("RGB", (64, 48), "gray"), cols=30, rows=7)

    assert len(cells) == 7
    assert all(len(row) == 30 for row in cells)


def test_brightness_picks_ramp_symbols():
    assert chars(image_to_cells(Image.new("RGB", (10, 10), "black"), 5, 5)) == {" "}
    assert chars(image_to_cells(Image.new("RGB", (10, 10), "white"), 5, 5)) == {"@"}


@pytest.mark.parametrize(
    ("start", "end", "symbol"),
    [
        ((5, 50), (195, 50), "-"),
        ((100, 5), (100, 95), "|"),
        ((10, 90), (190, 10), "/"),
        ((10, 10), (190, 90), "\\"),
    ],
)
def test_contours_are_drawn_with_matching_line_symbols(start, end, symbol):
    # 20x20 cells over 200x100 px keeps 45 degree lines at 45 degrees on screen.
    cells = image_to_cells(line_image(start, end), cols=20, rows=20)

    edge_symbols = chars(cells) & set(ASCII.edges)
    assert edge_symbols == {symbol}


def gradient_symbols(charset):
    image = Image.linear_gradient("L").rotate(90).convert("RGB")  # dark left, bright right
    edgeless = Charset(ramp=charset.ramp, levels=charset.levels)
    return image_to_cells(image, 256, 1, edgeless)[0]


@pytest.mark.parametrize("charset", [ASCII, UNICODE])
def test_brighter_cells_never_get_emptier_symbols(charset):
    ranks = [charset.ramp.index(cell.char) for cell in gradient_symbols(charset)]

    assert ranks == sorted(ranks)


def test_unicode_shows_more_shades_than_ascii():
    ascii_shades = {cell.char for cell in gradient_symbols(ASCII)}
    unicode_shades = {cell.char for cell in gradient_symbols(UNICODE)}

    assert len(unicode_shades) > 2 * len(ascii_shades)


def test_edges_can_be_disabled():
    cells = image_to_cells(line_image((5, 50), (195, 50)), 20, 10, Charset(ramp=" #"))

    assert chars(cells) <= {" ", "#"}


def test_unicode_charset_uses_unicode_symbols(data_dir):
    text = image_to_text(load_image(data_dir / "acacia.png"), 60, 20, UNICODE, color=False)

    assert set(text) - {"\n"} <= set(UNICODE.ramp + UNICODE.edges)
    assert set(text) & set(UNICODE.edges)


def test_cells_keep_image_colors():
    image = Image.new("RGB", (20, 10), (200, 0, 0))
    image.paste((0, 0, 200), (10, 0, 20, 10))

    left, right = image_to_cells(image, 2, 1)[0]

    assert (left.color, right.color) == (9, 12)  # bright red, bright blue


def test_render_ansi_colors_each_line_and_resets():
    cells = image_to_cells(Image.new("RGB", (20, 10), "white"), 4, 2)

    assert render_ansi(cells).split("\n") == ["\x1b[97m@@@@\x1b[0m"] * 2
    assert render_plain(cells) == "@@@@\n@@@@"


def test_sample_image_fits_terminal(data_dir):
    text = image_to_text(load_image(data_dir / "shapes.png"), 80, 24, color=False)
    lines = text.split("\n")

    assert len(lines) <= 24
    assert all(len(line) <= 80 for line in lines)


def test_transparent_image_is_shown_on_black(tmp_path):
    path = tmp_path / "transparent.png"
    Image.new("RGBA", (10, 10), (255, 255, 255, 0)).save(path)

    assert load_image(path).getpixel((5, 5)) == (0, 0, 0)


def test_dithering_mixes_neighbouring_symbols_to_match_the_shade():
    # Coverage 0.5 sits between ASCII's "+" (4/9) and "=" (5/9).
    image = Image.new("RGB", (40, 20), (128, 128, 128))

    plain = image_to_cells(image, 40, 20)
    dithered = image_to_cells(image, 40, 20, dither=True)

    assert chars(plain) == {"="}
    assert chars(dithered) == {"+", "="}
    coverage = [ASCII.ramp.index(cell.char) / 9 for row in dithered for cell in row]
    assert sum(coverage) / len(coverage) == pytest.approx(128 / 255, abs=0.01)


@pytest.mark.parametrize("fill", ["black", "white"])
def test_dithering_leaves_exact_shades_alone(fill):
    image = Image.new("RGB", (20, 10), fill)

    assert image_to_cells(image, 20, 10, dither=True) == image_to_cells(image, 20, 10)


def test_dithering_leaves_palette_hues_alone():
    cells = image_to_cells(Image.new("RGB", (20, 10), (0, 200, 0)), 20, 10, dither=True)

    assert {cell.color for row in cells for cell in row} == {10}  # bright green


@pytest.mark.parametrize(
    ("rgb", "mix"),
    [
        ((255, 128, 0), {9, 11}),  # orange: bright red and bright yellow
        ((255, 130, 255), {13, 15}),  # pink: bright magenta and bright white
    ],
)
def test_dithering_mixes_terminal_colors_for_hues_in_between(rgb, mix):
    image = Image.new("RGB", (20, 10), rgb)

    colors = {cell.color for row in image_to_cells(image, 20, 10, dither=True) for cell in row}

    assert colors == mix


def test_levels_must_grow_with_the_ramp():
    with pytest.raises(ValueError):
        Charset(ramp=" .#", levels=(0.0, 0.6, 0.3))
