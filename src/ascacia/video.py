from collections.abc import Iterator
from fractions import Fraction
from os import PathLike
from typing import Any

from PIL import Image

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


class VideoFrame:
    def __init__(self, time: float, frame: Any, display_size: tuple[int, int]):
        self.time = time
        self._frame = frame
        self._display_size = display_size

    def to_image(self, width: int | None = None, height: int | None = None) -> Image.Image:
        """The frame as an RGB image, scaled by the decoder (much faster than Pillow)."""
        display_width, display_height = self._display_size
        return self._frame.to_image(width=width or display_width, height=height or display_height)


class Video:
    """A video file decoded with PyAV, which comes with the optional ``video`` extra."""

    def __init__(self, path: str | PathLike):
        av = _import_av()
        try:
            self._container = av.open(str(path))
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
