from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")

# Floyd-Steinberg: (dx, dy, share of the error) for the neighbours not visited yet.
_SPREAD = ((1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16))


def diffuse(
    values: Sequence[Sequence[float]],
    cols: int,
    quantize: Callable[[int, list[float]], tuple[T, Sequence[float]]],
) -> list[T]:
    """Quantize a row-major grid, pushing each cell's error onto the cells after it.

    ``quantize`` gets a cell's index and its channels with the error carried in, and
    returns the chosen result together with the error left to pass on.
    """
    rows = len(values) // cols
    errors = [[0.0] * len(value) for value in values]
    results: list[T] = [None] * len(values)  # type: ignore[list-item]
    for y in range(rows):
        # Going back and forth keeps the error from piling up into diagonal streaks.
        step = 1 if y % 2 == 0 else -1
        for x in range(cols) if step == 1 else range(cols - 1, -1, -1):
            i = y * cols + x
            wanted = [value + error for value, error in zip(values[i], errors[i], strict=True)]
            results[i], error = quantize(i, wanted)
            for dx, dy, share in _SPREAD:
                nx, ny = x + dx * step, y + dy
                if 0 <= nx < cols and ny < rows:
                    target = errors[ny * cols + nx]
                    for channel, amount in enumerate(error):
                        target[channel] += amount * share
    return results
