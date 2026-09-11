"""Ghép filtergraph render và chọn định dạng."""
import pytest

from pipeline.layout import compute_vertical_layout
from pipeline.s7_render import build_render_filter, le_doc_phu_de, parse_formats

PRESET = {"facecam": {"x": 1440, "y": 810, "w": 480, "h": 270},
          "doc": {"kieu": "cam_tren", "gameplay_center_x": 960, "ti_le_cam": 0.32}}
LAYOUT = compute_vertical_layout(1920, 1080, PRESET)


def test_parse_formats():
    assert parse_formats("ngang") == ["ngang"]
    assert parse_formats("doc") == ["doc"]
    assert parse_formats("ca-hai") == ["ngang", "doc"]
    assert parse_formats("CA-HAI") == ["ngang", "doc"]
    with pytest.raises(ValueError):
        parse_formats("vuong")


def test_filter_ngang_khong_phu_de_la_no_op():
    f = build_render_filter("ngang", LAYOUT)
    assert f == "[0:v]setsar=1[base];[base]null[v]"


def test_filter_ngang_co_phu_de():
    f = build_render_filter("ngang", LAYOUT, ass_name="c01_ngang.ass")
    assert f.endswith("[base]ass=c01_ngang.ass[v]")


def test_filter_doc_ghep_layout_roi_phu_de():
    f = build_render_filter("doc", LAYOUT, ass_name="c01_doc.ass")
    assert "vstack=inputs=2[base]" in f
    assert f.endswith("[base]ass=c01_doc.ass[v]")
    assert f.count("[v]") == 1                 # chỉ một nhãn ra


def test_filter_preview_thu_nho_truoc_khi_burn():
    f = build_render_filter("doc", LAYOUT, ass_name="c01_doc.ass", cao_preview=480)
    assert "[base]scale=-2:480,ass=c01_doc.ass[v]" in f


def test_ten_file_ass_la_duong_dan_tuong_doi():
    """FFmpeg chạy với cwd = thư mục chứa .ass, nên trong filter không được có `:` hay `\\`."""
    f = build_render_filter("doc", LAYOUT, ass_name="c01_doc.ass")
    sau_ass = f.split("ass=")[1]
    assert ":" not in sau_ass and "\\" not in sau_ass


def test_le_doc_phu_de_nam_duoi_facecam():
    style = {"doc": {"le_doc": 40}}
    assert le_doc_phu_de("doc", LAYOUT, style) == LAYOUT["h_cam"] + 40
    assert le_doc_phu_de("ngang", LAYOUT, style) is None
    # kiểu khong_cam không có facecam -> dùng lề mặc định trong style
    khong_cam = compute_vertical_layout(1920, 1080, {"doc": {"kieu": "khong_cam"}})
    assert le_doc_phu_de("doc", khong_cam, style) is None


def test_filter_them_fontsdir():
    f = build_render_filter("doc", LAYOUT, ass_name="c01_doc.ass", fontsdir="../../../assets/fonts")
    assert f.endswith("[base]ass=c01_doc.ass:fontsdir=../../../assets/fonts[v]")
    assert "\\" not in f              # đường dẫn phải dùng dấu / để khỏi phải escape


def test_fontsdir_bo_qua_khi_thu_muc_khong_co_font(tmp_path, monkeypatch):
    import pipeline.s7_render as s7
    monkeypatch.setattr(s7, "FONTS_DIR", tmp_path / "khong-ton-tai")
    assert s7.fontsdir_tuong_doi(tmp_path) is None

    trong = tmp_path / "fonts"
    trong.mkdir()
    (trong / "README.md").write_text("khong phai font", encoding="utf-8")
    monkeypatch.setattr(s7, "FONTS_DIR", trong)
    assert s7.fontsdir_tuong_doi(tmp_path) is None

    (trong / "BeVietnamPro.ttf").write_bytes(b"gia lap")
    assert s7.fontsdir_tuong_doi(tmp_path) == "fonts"
