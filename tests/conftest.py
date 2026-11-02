from pathlib import Path

import pytest
from PIL import Image

DATA = Path(__file__).parent / "data"


@pytest.fixture
def data_dir() -> Path:
    return DATA


@pytest.fixture(scope="session")
def video_path(tmp_path_factory) -> Path:
    """Two seconds at 10 fps, getting brighter every frame."""
    av = pytest.importorskip("av")
    path = tmp_path_factory.mktemp("video") / "clip.mp4"
    with av.open(str(path), "w") as container:
        stream = container.add_stream("mpeg4", rate=10)
        stream.width, stream.height, stream.pix_fmt = 64, 32, "yuv420p"
        for i in range(20):
            frame = av.VideoFrame.from_image(Image.new("RGB", (64, 32), (i * 12,) * 3))
            container.mux(stream.encode(frame))
        container.mux(stream.encode())
    return path
