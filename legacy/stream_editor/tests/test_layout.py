"""Layout dọc 1080x1920 — kích thước, quy đổi toạ độ, chuỗi filter."""
import re

import pytest

from pipeline.layout import build_vertical_filter, compute_vertical_layout

PRESET = {
    "facecam": {"x": 1440, "y": 810, "w": 480, "h": 270},
    "doc": {"kieu": "cam_tren", "gameplay_center_x": 960, "ti_le_cam": 0.32},
}


def _so_trong_filter(f: str) -> list[int]:
    """Mọi tham số số của crop=/scale= (bỏ qua -2 = 'FFmpeg tự tính cho chẵn')."""
    nums = []
    for m in re.finditer(r"(?:crop|scale)=([-\d:]+)", f):
        nums += [int(x) for x in m.group(1).split(":") if re.fullmatch(r"-?\d+", x)]
    return [n for n in nums if n > 0]


def test_cam_tren_chia_doi_dung_chieu_cao():
    L = compute_vertical_layout(1920, 1080, PRESET)
    assert L["kieu"] == "cam_tren"
    assert L["h_cam"] + L["h_game"] == 1920      # vstack phải ra đúng 1920
    assert round(L["h_cam"] / 1920, 2) == 0.32
    assert L["canh_bao"] is None


def test_moi_kich_thuoc_deu_chan():
    """libx264 từ chối cạnh lẻ — lỗi này chỉ lộ ra lúc render nên phải chặn ở đây."""
    for src in [(1920, 1080), (2560, 1440), (1280, 720), (1600, 900), (1918, 1078)]:
        L = compute_vertical_layout(*src, PRESET)
        for key in ("out_w", "out_h", "h_cam", "h_game"):
            assert L[key] % 2 == 0, (src, key, L[key])
        for vung in ("cam", "game"):
            assert all(v % 2 == 0 for v in L[vung]), (src, vung, L[vung])
        assert all(n % 2 == 0 for n in _so_trong_filter(build_vertical_filter(*src, PRESET)))


def test_quy_doi_toa_do_khi_nguon_khong_phai_1080p():
    """Toạ độ facecam đo trên khung 1920x1080 phải scale theo nguồn thật."""
    L = compute_vertical_layout(2560, 1440, PRESET)   # gấp 4/3
    x, y, w, h = L["cam"]
    assert (x, y, w, h) == (1920, 1080, 640, 360)


def test_vung_cat_luon_nam_trong_khung():
    preset = {**PRESET, "facecam": {"x": 1800, "y": 1000, "w": 480, "h": 270}}  # tràn ra ngoài
    L = compute_vertical_layout(1920, 1080, preset)
    x, y, w, h = L["cam"]
    assert x + w <= 1920 and y + h <= 1080
    gx, gy, gw, gh = L["game"]
    assert gx + gw <= 1920 and gy + gh <= 1080


def test_ti_le_cam_bi_kep_trong_khoang_hop_ly():
    L = compute_vertical_layout(1920, 1080, {**PRESET, "doc": {"kieu": "cam_tren", "ti_le_cam": 0.9}})
    assert L["h_cam"] <= 1920 * 0.5
    L = compute_vertical_layout(1920, 1080, {**PRESET, "doc": {"kieu": "cam_tren", "ti_le_cam": 0.01}})
    assert L["h_cam"] >= 1920 * 0.15 - 2


def test_khong_cam_dung_nen_mo():
    f = build_vertical_filter(1920, 1080, {"doc": {"kieu": "khong_cam"}})
    assert "boxblur" in f and "overlay=" in f
    assert "vstack" not in f
    assert f.endswith("[v]")


def test_thieu_facecam_thi_tu_chuyen_sang_khong_cam():
    L = compute_vertical_layout(1920, 1080, {"doc": {"kieu": "cam_tren"}})
    assert L["kieu"] == "khong_cam"
    assert "facecam" in L["canh_bao"]


def test_filter_cam_tren_du_cac_manh():
    f = build_vertical_filter(1920, 1080, PRESET)
    assert f.startswith("[0:v]split=2")
    assert "vstack=inputs=2[v]" in f
    assert f.count("setsar=1") == 2          # cả hai nhánh, tránh lệch tỉ lệ điểm ảnh


def test_doi_duoc_nhan_dau_ra():
    f = build_vertical_filter(1920, 1080, PRESET, nhan_ra="base")
    assert f.endswith("[base]") and "[v]" not in f


@pytest.mark.parametrize("kieu", ["cam_tren", "khong_cam"])
def test_kich_thuoc_dau_ra_dung_1080x1920(kieu):
    L = compute_vertical_layout(1920, 1080, {**PRESET, "doc": {**PRESET["doc"], "kieu": kieu}})
    assert (L["out_w"], L["out_h"]) == (1080, 1920)
