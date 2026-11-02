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


def test_video_is_not_implemented_yet(data_dir, capsys):
    assert video_main([str(data_dir / "acacia.png")]) == 2
    assert "not implemented" in capsys.readouterr().err
