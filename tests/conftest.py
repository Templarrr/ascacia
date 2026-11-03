from contextlib import ExitStack
from pathlib import Path

import pytest
from PIL import Image

DATA = Path(__file__).parent / "data"


@pytest.fixture
def data_dir() -> Path:
    return DATA


EMBEDDED_SRT = (
    "1\n00:00:00,500 --> 00:00:01,200\n<i>Hello</i>, there\n\n"
    "2\n00:00:01,300 --> 00:00:01,900\nTwo\nlines\n"
)


def _write_video(path: Path, subtitles: list[tuple[str, str]] = ()) -> Path:
    """Two seconds at 10 fps, getting brighter every frame, plus ``(language, srt)`` tracks."""
    av = pytest.importorskip("av")
    with ExitStack() as stack:
        container = stack.enter_context(av.open(str(path), "w"))
        stream = container.add_stream("mpeg4", rate=10)
        stream.width, stream.height, stream.pix_fmt = 64, 32, "yuv420p"
        # FFmpeg's own .srt reader gives ready-made packets to copy in; every track has to
        # exist before the first packet is written.
        copies = []
        for number, (language, text) in enumerate(subtitles):
            srt_path = path.with_name(f"{path.stem}.track{number}.txt")
            srt_path.write_text(text)
            source = stack.enter_context(av.open(str(srt_path), format="srt"))
            track = container.add_stream_from_template(source.streams.subtitles[0])
            track.metadata["language"] = language
            track.metadata["title"] = f"{language} subs"
            copies.append((source, track))
        for source, track in copies:
            for packet in source.demux(source.streams.subtitles[0]):
                if packet.dts is not None:
                    packet.stream = track
                    container.mux(packet)
        for i in range(20):
            frame = av.VideoFrame.from_image(Image.new("RGB", (64, 32), (i * 12,) * 3))
            container.mux(stream.encode(frame))
        container.mux(stream.encode())
    return path


@pytest.fixture(scope="session")
def video_path(tmp_path_factory) -> Path:
    return _write_video(tmp_path_factory.mktemp("video") / "clip.mp4")


@pytest.fixture(scope="session")
def subtitled_video_path(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("subtitled") / "clip.mkv"
    french = EMBEDDED_SRT.replace("Hello", "Bonjour")
    return _write_video(path, [("eng", EMBEDDED_SRT), ("fre", french)])
