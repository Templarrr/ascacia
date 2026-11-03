import pytest

from ascacia import (
    Cue,
    ass_dialogue_text,
    find_subtitles,
    format_time,
    load_subtitles,
    lyrics_lines,
    parse_subtitles,
    parse_time,
)

SRT = (
    "1\r\n00:00:01,000 --> 00:00:02,500\r\n<i>Hello</i> there\r\n\r\n"
    "2\r\n00:00:03,000 --> 00:00:04,000\r\n{\\an8}Two\r\nlines\r\n"
)
VTT = """WEBVTT

NOTE this is not a cue

intro
00:01.000 --> 00:02.500 align:start
<v Narrator>Hello there

01:00:03.000 --> 01:00:04.000
Later
"""


def test_parse_srt_strips_markup():
    assert parse_subtitles(SRT) == [
        Cue(1.0, 2.5, "Hello there"),
        Cue(3.0, 4.0, "Two\nlines"),
    ]


def test_parse_vtt_skips_header_notes_and_settings():
    assert parse_subtitles(VTT) == [
        Cue(1.0, 2.5, "Hello there"),
        Cue(3603.0, 3604.0, "Later"),
    ]


def test_ass_dialogue_text():
    line = r"0,0,Default,,0,0,0,,{\i1}Hello{\i0},\hthere\NTwo"
    assert ass_dialogue_text(line) == "Hello, there\nTwo"


def test_load_legacy_encoded_file(tmp_path):
    path = tmp_path / "movie.srt"
    path.write_bytes("1\n00:00:01,000 --> 00:00:02,000\nCafé\n".encode("cp1252"))

    assert load_subtitles(path) == [Cue(1.0, 2.0, "Café")]


def test_find_subtitles_next_to_video(tmp_path):
    video = tmp_path / "movie [2024].mkv"
    for name in (
        "movie [2024].en.forced.srt",
        "movie [2024].en.srt",
        "other.srt",
        "movie [2024].nfo",
    ):
        (tmp_path / name).write_text("")

    assert find_subtitles(video) == tmp_path / "movie [2024].en.srt"

    (tmp_path / "movie [2024].vtt").write_text("")
    assert find_subtitles(video) == tmp_path / "movie [2024].vtt"


def test_find_subtitles_when_there_are_none(tmp_path):
    assert find_subtitles(tmp_path / "movie.mp4") is None


CUES = [Cue(i * 10, i * 10 + 5, f"line {i}") for i in range(10)]


def test_lyrics_highlight_current_cue_and_show_neighbours():
    lines = lyrics_lines(CUES, 52, width=20, height=9)

    assert len(lines) == 9
    assert lines[3] == ("line 5", True)
    assert ("line 4", False) in lines[:3]
    assert ("line 6", False) in lines[4:]
    assert [text for text, current in lines if current] == ["line 5"]


def test_lyrics_between_cues_show_the_next_one_dimmed():
    lines = lyrics_lines(CUES, 57, width=20, height=9)

    assert lines[3] == ("line 6", False)
    assert not any(current for _, current in lines)


def test_lyrics_wrap_long_cues():
    lines = lyrics_lines([Cue(0, 5, "a few words that need wrapping")], 1, width=10, height=6)

    texts = [text for text, current in lines if current]
    assert texts == ["a few", "words that", "need", "wrapping"]


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("90", 90), ("1:30", 90), ("1:02:03.5", 3723.5), ("00:00:01,250", 1.25)],
)
def test_parse_time(text, seconds):
    assert parse_time(text) == seconds


@pytest.mark.parametrize("text", ["", "abc", "1:-2", "1:2:3:4"])
def test_parse_time_rejects_garbage(text):
    with pytest.raises(ValueError):
        parse_time(text)


def test_format_time():
    assert format_time(83) == "01:23"
    assert format_time(3723.9) == "1:02:03"
