import sys

import pytest

from ascacia import image_to_text, load_image
from ascacia.cli import image_main, video_main


def test_image_print_mode_fits_requested_size(data_dir, capsys):
    code = image_main(
        [str(data_dir / "acacia.png"), "--print", "--no-color", "--cols", "50", "--rows", "15"]
    )

    lines = capsys.readouterr().out.rstrip("\n").split("\n")
    assert code == 0
    assert len(lines) <= 15
    assert all(len(line) <= 50 for line in lines)


def test_image_print_mode_with_custom_ramp(data_dir, capsys):
    image_main(
        [str(data_dir / "gradient.png"), "--print", "--no-color", "--no-edges", "--ramp", " o"]
    )

    assert set(capsys.readouterr().out) <= {" ", "o", "\n"}


def test_missing_image_is_reported(tmp_path, capsys):
    assert image_main([str(tmp_path / "missing.png"), "--print"]) == 1
    assert "no such file" in capsys.readouterr().err


def test_non_image_file_is_reported(tmp_path, capsys):
    path = tmp_path / "notes.txt"
    path.write_text("not an image")

    assert image_main([str(path), "--print"]) == 1
    assert "not a supported image" in capsys.readouterr().err


def test_video_without_optional_dependencies_explains_how_to_install(data_dir, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "av", None)

    assert video_main([str(data_dir / "acacia.png")]) == 2
    assert "ascacia[video]" in capsys.readouterr().err


def test_missing_video_is_reported(tmp_path, capsys):
    pytest.importorskip("av")
    assert video_main([str(tmp_path / "missing.mp4")]) == 1
    assert "no such file" in capsys.readouterr().err


def test_non_video_file_is_reported(tmp_path, capsys):
    pytest.importorskip("av")
    path = tmp_path / "notes.txt"
    path.write_text("not a video")

    assert video_main([str(path)]) == 1
    assert "not a supported video" in capsys.readouterr().err


def test_missing_subtitle_file_is_reported(video_path, tmp_path, capsys):
    assert video_main([str(video_path), "--subtitles", str(tmp_path / "missing.srt")]) == 1
    assert "no such file" in capsys.readouterr().err


def test_video_player_needs_a_terminal(video_path, capsys):
    assert video_main([str(video_path)]) == 1
    assert "interactive terminal" in capsys.readouterr().err


@pytest.fixture
def played(monkeypatch):
    """Cues the player would get, without needing a terminal."""
    calls = []
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr("ascacia.cli.play_video", lambda video, cues, **_: calls.append(cues))
    return calls


def test_list_embedded_subtitles(subtitled_video_path, capsys):
    assert video_main([str(subtitled_video_path), "--list-subtitles"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("0 eng 'eng subs'")
    assert lines[1].startswith("1 fre 'fre subs'")


def test_first_embedded_track_is_shown_by_default(subtitled_video_path, played):
    assert video_main([str(subtitled_video_path)]) == 0
    assert played[0][0].text == "Hello, there"


def test_embedded_track_chosen_by_language(subtitled_video_path, played):
    assert video_main([str(subtitled_video_path), "--subtitle-track", "fre"]) == 0
    assert played[0][0].text == "Bonjour, there"


def test_subtitle_file_next_to_video_wins_over_embedded(subtitled_video_path, tmp_path, played):
    video = tmp_path / "movie.mkv"
    video.write_bytes(subtitled_video_path.read_bytes())
    (tmp_path / "movie.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nFrom file\n")

    assert video_main([str(video)]) == 0
    assert played[0][0].text == "From file"


def test_unknown_subtitle_track_is_reported(subtitled_video_path, capsys):
    assert video_main([str(subtitled_video_path), "--subtitle-track", "9"]) == 1
    assert "no subtitle track '9'" in capsys.readouterr().err


def test_image_print_mode_can_turn_dithering_on(data_dir, capsys):
    path = data_dir / "spheres.png"
    args = [str(path), "--print", "--cols", "40", "--rows", "12"]

    image_main(args)
    plain = capsys.readouterr().out
    image_main([*args, "--dither"])
    dithered = capsys.readouterr().out

    assert plain == image_to_text(load_image(path), 40, 12) + "\n"
    assert dithered != plain
