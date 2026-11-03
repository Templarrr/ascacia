import argparse
import shutil
import sys
from pathlib import Path

from PIL import UnidentifiedImageError

from .charsets import CHARSETS, Charset, supports_unicode
from .convert import DEFAULT_CELL_ASPECT, DEFAULT_EDGE_THRESHOLD, image_to_text, load_image
from .player import play_video
from .subtitles import Cue, find_subtitles, load_subtitles, parse_time
from .video import MissingVideoSupport, Video
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
        prog="ascacia_video",
        description="Play a video as colored text art in the terminal (no sound).",
    )
    _add_render_options(parser)
    chosen = parser.add_mutually_exclusive_group()
    chosen.add_argument(
        "--subtitles",
        type=Path,
        help="subtitle file (.srt or .vtt); by default one named like the video is used, "
        "else the first text track inside the video",
    )
    chosen.add_argument(
        "--subtitle-track",
        metavar="TRACK",
        help="subtitle track inside the video, by number or language (see --list-subtitles)",
    )
    chosen.add_argument("--no-subtitles", action="store_true", help="don't show subtitles")
    parser.add_argument(
        "--list-subtitles",
        action="store_true",
        help="list the subtitle tracks inside the video and exit",
    )
    parser.add_argument(
        "--start", type=parse_time, default=0.0, help="start at this time, e.g. 1:30 or 90"
    )
    args = parser.parse_args(argv)

    try:
        charset = _charset(args)
    except ValueError as error:
        parser.error(str(error))

    try:
        video = Video(args.path)
    except MissingVideoSupport as error:
        print(f"ascacia_video: {error}", file=sys.stderr)
        return 2
    except FileNotFoundError:
        print(f"ascacia_video: no such file: {args.path}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"ascacia_video: {error}", file=sys.stderr)
        return 1

    with video:
        if args.list_subtitles:
            for track in video.subtitle_tracks:
                print(track.describe())
            if not video.subtitle_tracks:
                print(f"ascacia_video: no subtitle tracks in {args.path}", file=sys.stderr)
            return 0
        try:
            cues = _subtitles(args, video)
        except FileNotFoundError:
            print(f"ascacia_video: no such file: {args.subtitles}", file=sys.stderr)
            return 1
        except ValueError as error:
            print(f"ascacia_video: {error}", file=sys.stderr)
            return 1

        if not sys.stdout.isatty():
            print("ascacia_video: needs an interactive terminal", file=sys.stderr)
            return 1
        play_video(
            video,
            cues,
            title=args.path.name,
            start=args.start,
            charset=charset,
            colors=args.colors,
            color=not args.no_color,
            cell_aspect=args.cell_aspect,
            edge_threshold=args.edge_threshold,
        )
    return 0


def _subtitles(args: argparse.Namespace, video: Video) -> list[Cue]:
    # A file given or lying next to the video wins over tracks inside it.
    if args.no_subtitles:
        return []
    if args.subtitles:
        path = args.subtitles
    elif args.subtitle_track is None:
        path = find_subtitles(args.path)
    else:
        path = None
    if path:
        cues = load_subtitles(path)
        if not cues:
            print(f"ascacia_video: no subtitles found in {path}", file=sys.stderr)
        return cues
    track = video.find_subtitle_track(args.subtitle_track)
    return video.read_subtitles(track) if track else []
