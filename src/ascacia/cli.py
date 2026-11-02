import argparse
import shutil
import sys
from pathlib import Path

from PIL import UnidentifiedImageError

from .charsets import CHARSETS, Charset, supports_unicode
from .convert import DEFAULT_CELL_ASPECT, DEFAULT_EDGE_THRESHOLD, image_to_text, load_image
from .video import play_video
from .viewer import view_image


def _add_render_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("path", type=Path, help="input file")
    parser.add_argument(
        "--charset",
        choices=sorted(CHARSETS),
        default="ascii",
        help="symbol set; unicode falls back to ascii if the terminal can't show it",
    )
    parser.add_argument("--ramp", help="custom symbols from emptiest to densest, e.g. ' .oO@'")
    parser.add_argument(
        "--no-edges", action="store_true", help="don't use line symbols for contours"
    )
    parser.add_argument("--colors", type=int, choices=(8, 16), default=16)
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument(
        "--cell-aspect",
        type=float,
        default=DEFAULT_CELL_ASPECT,
        help="height/width ratio of a terminal cell (default: %(default)s)",
    )
    parser.add_argument(
        "--edge-threshold",
        type=float,
        default=DEFAULT_EDGE_THRESHOLD,
        help="contour strength (0-1) needed to draw a line symbol (default: %(default)s)",
    )


def _charset(args: argparse.Namespace) -> Charset:
    charset = CHARSETS[args.charset]
    if charset.unicode and not supports_unicode():
        print("ascacia: terminal encoding is not UTF-8, using ascii", file=sys.stderr)
        charset = CHARSETS["ascii"]
    return Charset(
        ramp=args.ramp or charset.ramp,
        edges="" if args.no_edges else charset.edges,
        unicode=charset.unicode,
        levels=None if args.ramp else charset.levels,
    )


def image_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ascacia_image", description="Show an image as colored text art in the terminal."
    )
    _add_render_options(parser)
    parser.add_argument(
        "--print",
        action="store_true",
        help="write the art to stdout instead of opening the viewer (implied when piped)",
    )
    parser.add_argument("--cols", type=int, help="max width in symbols (default: terminal width)")
    parser.add_argument("--rows", type=int, help="max height in lines (default: terminal height)")
    args = parser.parse_args(argv)

    try:
        image = load_image(args.path)
    except FileNotFoundError:
        print(f"ascacia_image: no such file: {args.path}", file=sys.stderr)
        return 1
    except UnidentifiedImageError:
        print(f"ascacia_image: not a supported image: {args.path}", file=sys.stderr)
        return 1

    try:
        charset = _charset(args)
    except ValueError as error:
        parser.error(str(error))
    options = {
        "charset": charset,
        "colors": args.colors,
        "color": not args.no_color,
        "cell_aspect": args.cell_aspect,
        "edge_threshold": args.edge_threshold,
    }

    if args.print or not sys.stdout.isatty():
        size = shutil.get_terminal_size()
        cols = args.cols or size.columns
        rows = args.rows or size.lines - 1
        print(image_to_text(image, cols, rows, **options))
    else:
        view_image(image, title=args.path.name, **options)
    return 0


def video_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ascacia_video", description="Play a video as colored text art in the terminal."
    )
    _add_render_options(parser)
    args = parser.parse_args(argv)
    try:
        play_video(args.path)
    except NotImplementedError as error:
        print(f"ascacia_video: {error}", file=sys.stderr)
        return 2
    return 0
