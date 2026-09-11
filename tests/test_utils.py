import pytest

from automeme.utils.files import read_json, write_json
from automeme.utils.timestamps import format_ts, parse_ts


@pytest.mark.parametrize("sec, text", [
    (0, "00:00.00"),
    (13.2, "00:13.20"),
    (8.73, "00:08.73"),
    (75.5, "01:15.50"),
    (3723.5, "1:02:03.50"),
])
def test_format_ts(sec, text):
    assert format_ts(sec) == text


def test_format_ts_so_am_ve_0():
    assert format_ts(-1) == "00:00.00"


@pytest.mark.parametrize("text, sec", [
    ("13.2", 13.2),
    ("00:13.20", 13.2),
    ("1:02:03.5", 3723.5),
    (" 01:15.50 ", 75.5),
    (8.73, 8.73),
    (5, 5.0),
])
def test_parse_ts(text, sec):
    assert parse_ts(text) == pytest.approx(sec)


@pytest.mark.parametrize("bad", ["", "abc", "1:75", "1::2", "-5", "1:2:3:4", "00:-3"])
def test_parse_ts_sai_dinh_dang(bad):
    with pytest.raises(ValueError, match="không hợp lệ"):
        parse_ts(bad)


@pytest.mark.parametrize("sec", [0, 0.01, 13.2, 59.99, 3599.99, 3723.5])
def test_format_parse_khu_nhau(sec):
    assert parse_ts(format_ts(sec)) == pytest.approx(sec)


def test_json_giu_dau_tieng_viet_va_khong_de_file_tam(tmp_path):
    path = tmp_path / "con" / "transcript.json"
    data = {"text": "Vợ tôi giữ hộ.", "start": 7.12}
    write_json(path, data)
    assert read_json(path) == data
    assert "Vợ tôi giữ hộ." in path.read_text(encoding="utf-8")  # không bị \uXXXX
    assert list(path.parent.iterdir()) == [path]
