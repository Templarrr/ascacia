import pytest

from ascacia import nearest_color


@pytest.mark.parametrize(
    ("rgb", "expected"),
    [
        ((250, 10, 10), 9),  # bright red
        ((120, 0, 0), 1),  # dark red keeps the hue instead of turning black
        ((20, 160, 30), 2),  # green
        ((240, 230, 40), 11),  # bright yellow
        ((128, 128, 128), 7),  # gray
        ((0, 0, 0), 7),  # never black ink, it would vanish on a dark background
    ],
)
def test_nearest_color(rgb, expected):
    assert nearest_color(rgb) == expected


def test_eight_color_palette_has_no_bright_variants():
    assert nearest_color((255, 0, 0), colors=8) == 1
