"""Bảng của lệnh `doctor` và `inspect`."""
from pipeline.diagnostics import FAIL, OK, WARN, format_checks, format_inspect_table


def test_format_checks_phan_loai_ba_trang_thai():
    rows = [("ffmpeg", FAIL, "không thấy"),
            ("ffplay", WARN, "tùy chọn"),
            ("numpy", OK, "bắt buộc")]
    out = format_checks(rows)
    assert "CẦN SỬA — ffmpeg" in out
    assert "Thiếu nhưng chưa chặn: ffplay" in out
    assert "numpy" in out


def test_format_checks_khi_moi_thu_dat():
    out = format_checks([("numpy", OK, "ok"), ("ffmpeg", OK, "/usr/bin/ffmpeg")])
    assert "tất cả đạt." in out
    assert "Thiếu nhưng chưa chặn" not in out


def test_format_inspect_table_rong():
    assert "Chạy bước candidates trước" in format_inspect_table([])


def test_format_inspect_table_co_du_lieu():
    rows = [{"id": "k01", "t": 605.0, "chat": 62.0, "chat_nen": 8.0, "loud": -12.3,
             "loud_nen": -21.4, "kw": 3.0, "p_chat": 0.72, "p_loudness": 0.45,
             "p_keywords": 0.6, "tong": 0.615}]
    out = format_inspect_table(rows)
    assert "k01" in out
    assert "0:10:05" in out          # 605 giây
    assert "+9.1" in out             # -12.3 so với nền -21.4
    assert "0.615" in out
