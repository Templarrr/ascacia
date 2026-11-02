import pytest

from ascacia import Video


def test_video_properties(video_path):
    with Video(video_path) as video:
        assert (video.width, video.height) == (64, 32)
        assert video.fps == 10
        assert video.duration == pytest.approx(2.0)


def test_frames_play_in_order_from_the_start(video_path):
    with Video(video_path) as video:
        times = [frame.time for frame in video.frames()]

    assert times == pytest.approx([i / 10 for i in range(20)])


def test_frames_can_start_in_the_middle(video_path):
    with Video(video_path) as video:
        first = next(video.frames(1.0))
        image = first.to_image(16, 8)

    assert first.time == pytest.approx(1.0)
    assert image.size == (16, 8)
    assert image.getpixel((8, 4))[0] == pytest.approx(120, abs=8)


def test_non_video_file_is_rejected(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("not a video")

    with pytest.raises(ValueError, match="not a supported video"):
        Video(path)


def test_missing_video_file(tmp_path):
    pytest.importorskip("av")
    with pytest.raises(FileNotFoundError):
        Video(tmp_path / "missing.mp4")
