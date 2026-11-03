import pytest

from ascacia import Cue, SubtitleTrack, Video


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


def test_video_without_subtitle_tracks(video_path):
    with Video(video_path) as video:
        assert video.subtitle_tracks == []
        assert video.find_subtitle_track() is None


def test_embedded_subtitle_tracks(subtitled_video_path):
    with Video(subtitled_video_path) as video:
        tracks = [(t.number, t.language, t.title, t.is_text) for t in video.subtitle_tracks]
        assert tracks == [(0, "eng", "eng subs", True), (1, "fre", "fre subs", True)]
        assert video.find_subtitle_track() == video.subtitle_tracks[0]
        assert video.find_subtitle_track("fre") == video.subtitle_tracks[1]
        assert video.find_subtitle_track(1) == video.subtitle_tracks[1]


def test_read_embedded_subtitles(subtitled_video_path):
    with Video(subtitled_video_path) as video:
        cues = video.read_subtitles(video.find_subtitle_track("fre"))
        # Reading them doesn't disturb playback.
        first = next(video.frames())

    assert cues == [Cue(0.5, 1.2, "Bonjour, there"), Cue(1.3, 1.9, "Two\nlines")]
    assert first.time == 0


def test_unknown_subtitle_track(subtitled_video_path):
    with Video(subtitled_video_path) as video, pytest.raises(ValueError, match="no subtitle track"):
        video.find_subtitle_track("ger")


def test_bitmap_subtitles_are_refused(subtitled_video_path):
    with Video(subtitled_video_path) as video, pytest.raises(ValueError, match="picture"):
        video.read_subtitles(SubtitleTrack(0, "hdmv_pgs_subtitle"))
