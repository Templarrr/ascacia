from collections.abc import Iterator
from dataclasses import dataclass
from fractions import Fraction
from os import PathLike
from typing import Any

from PIL import Image

from .subtitles import Cue, ass_dialogue_text

INSTALL_HINT = (
    "video support is not installed; reinstall with the video extra, e.g.\n"
    '  uv tool install "ascacia[video] @ git+https://github.com/Templarrr/ascacia"\n'
    '  pip install "ascacia[video]"'
)


class MissingVideoSupport(ImportError):
    pass


def _import_av():
    try:
        import av
    except ImportError as error:
        raise MissingVideoSupport(INSTALL_HINT) from error
    return av


# Picture-based subtitles (Blu-ray PGS, DVD VobSub, ...) have no text for the panel.
BITMAP_SUBTITLE_CODECS = frozenset(
    {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub", "dvb_teletext"}
)
# For cues stored without a duration (shown until the next one).
_MAX_CUE_LENGTH = 5.0


@dataclass(frozen=True)
class SubtitleTrack:
    number: int
    codec: str
    language: str | None = None
    title: str | None = None

    @property
    def is_text(self) -> bool:
        return self.codec not in BITMAP_SUBTITLE_CODECS

    def describe(self) -> str:
        parts = [str(self.number), self.language or "und"]
        if self.title:
            parts.append(repr(self.title))
        parts.append(f"({self.codec}{'' if self.is_text else ', bitmap: not supported'})")
        return " ".join(parts)


class VideoFrame:
    def __init__(self, time: float, frame: Any, display_size: tuple[int, int]):
        self.time = time
        self._frame = frame
        self._display_size = display_size

    def to_image(self, width: int | None = None, height: int | None = None) -> Image.Image:
        """The frame as an RGB image, scaled by the decoder (much faster than Pillow)."""
        display_width, display_height = self._display_size
        return self._frame.to_image(width=width or display_width, height=height or display_height)


def _decoded_texts(packet) -> Iterator[str]:
    for decoded in packet.decode():
        # PyAV 14+ yields one subtitle per item, older versions a set of them.
        for subtitle in decoded if hasattr(decoded, "__iter__") else [decoded]:
            line = getattr(subtitle, "ass", None)
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            text = ass_dialogue_text(line) if line else ""
            if text:
                yield text


class Video:
    """A video file decoded with PyAV, which comes with the optional ``video`` extra."""

    def __init__(self, path: str | PathLike):
        av = _import_av()
        self._path = str(path)
        try:
            self._container = av.open(self._path)
        except FileNotFoundError:
            # PyAV's own FileNotFoundError is also an FFmpegError; keep it a plain one.
            raise
        except av.FFmpegError as error:
            raise ValueError(f"not a supported video: {path}") from error
        if not self._container.streams.video:
            self._container.close()
            raise ValueError(f"no video stream in {path}")
        stream = self._container.streams.video[0]
        stream.thread_type = "AUTO"
        self._stream = stream
        self._time_base = stream.time_base or Fraction(1, 1_000_000)
        self._start = float(stream.start_time * self._time_base) if stream.start_time else 0.0

        # Some videos store squeezed pixels that players stretch back out.
        aspect = stream.sample_aspect_ratio
        self.width = round(stream.width * aspect) if aspect else stream.width
        self.height = stream.height
        rate = stream.average_rate or stream.guessed_rate
        self.fps = float(rate) if rate else 25.0
        if stream.duration:
            self.duration = float(stream.duration * self._time_base)
        elif self._container.duration:
            self.duration = self._container.duration / 1_000_000
        else:
            self.duration = 0.0
        self.subtitle_tracks = [
            SubtitleTrack(
                number,
                stream.codec_context.name,
                stream.language if stream.language not in (None, "und") else None,
                stream.metadata.get("title"),
            )
            for number, stream in enumerate(self._container.streams.subtitles)
        ]

    def find_subtitle_track(self, choice: str | int | None = None) -> SubtitleTrack | None:
        """Track by number or language code; with no choice, the first text track (if any)."""
        if choice is None:
            return next((track for track in self.subtitle_tracks if track.is_text), None)
        for track in self.subtitle_tracks:
            if str(choice) == str(track.number) or str(choice).lower() == track.language:
                return track
        raise ValueError(f"no subtitle track {choice!r} in {self._path}")

    def read_subtitles(self, track: SubtitleTrack) -> list[Cue]:
        """All cues of an embedded text subtitle track, timed like the frames."""
        if not track.is_text:
            raise ValueError(f"subtitle track {track.number} is a picture format ({track.codec})")
        av = _import_av()
        # A separate container, so reading the whole file doesn't move the playback position.
        with av.open(self._path) as container:
            stream = container.streams.subtitles[track.number]
            time_base = stream.time_base or Fraction(1, 1000)
            timed = []
            for packet in container.demux(stream):
                if packet.pts is None:
                    continue
                start = float(packet.pts * time_base) - self._start
                length = float(packet.duration * time_base) if packet.duration else None
                text = "\n".join(_decoded_texts(packet))
                if text:
                    timed.append((start, length, text))
        timed.sort(key=lambda item: item[0])
        cues = []
        for i, (start, length, text) in enumerate(timed):
            if length is None:
                following = timed[i + 1][0] if i + 1 < len(timed) else start + _MAX_CUE_LENGTH
                length = min(following - start, _MAX_CUE_LENGTH)
            cues.append(Cue(start, start + length, text))
        return cues

    def frames(self, start: float = 0.0) -> Iterator[VideoFrame]:
        """Frames in order from ``start`` seconds; times count from the start of the video."""
        start = max(start, 0.0)
        self._container.seek(int((start + self._start) / self._time_base), stream=self._stream)
        # Seeking lands on the keyframe before ``start``; decode up to the wanted frame.
        threshold = start - 0.5 / self.fps
        previous = start
        for frame in self._container.decode(self._stream):
            time = frame.time - self._start if frame.time is not None else previous
            previous = time + 1 / self.fps
            if time >= threshold:
                yield VideoFrame(time, frame, (self.width, self.height))

    def close(self) -> None:
        self._container.close()

    def __enter__(self) -> "Video":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
