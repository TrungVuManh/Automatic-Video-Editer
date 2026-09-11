"""Dựng filtergraph cho định dạng dọc 1080×1920 (Shorts/TikTok).

Toàn bộ là hàm thuần: tính toạ độ rồi ghép chuỗi filter. Không gọi FFmpeg ở đây.

Hai kiểu (`doc.kieu` trong preset streamer):
- `cam_tren`  — facecam cắt từ toạ độ preset đặt trên, gameplay đặt dưới, ghép bằng vstack.
- `khong_cam` — nền là chính khung hình phóng to + làm mờ, gameplay đặt giữa.
"""
from __future__ import annotations

OUT_W, OUT_H = 1080, 1920
# Toạ độ facecam trong preset được đo trên khung tham chiếu này; nguồn khác sẽ quy đổi theo tỉ lệ.
REF_W, REF_H = 1920, 1080

DOC_MAC_DINH = {
    "kieu": "cam_tren",
    "gameplay_center_x": REF_W // 2,
    "ti_le_cam": 0.32,
}
TI_LE_CAM_MIN, TI_LE_CAM_MAX = 0.15, 0.50


def _chan(n: float, toi_thieu: int = 2) -> int:
    """Làm tròn XUỐNG số chẵn — libx264 yêu cầu cạnh chẵn.

    Luôn tròn xuống chứ không tròn gần nhất: với kích thước, tròn lên có thể vượt quá
    khung nguồn; với toạ độ, tròn lên có thể đẩy vùng cắt ra ngoài. `toi_thieu` là 2 cho
    kích thước (cạnh không thể bằng 0) và 0 cho toạ độ (gốc 0 là hợp lệ).
    """
    return max(toi_thieu, int(n // 2) * 2)


def _kep(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def compute_vertical_layout(src_w: int, src_h: int, preset: dict,
                            out_w: int = OUT_W, out_h: int = OUT_H) -> dict:
    """Tính mọi kích thước/toạ độ của khung dọc. Mọi số trả về đều chẵn.

    Trả về dict có `kieu`, `h_cam`, `h_game`, `cam` (x, y, w, h trên khung nguồn) và
    `game`; `canh_bao` khác None khi phải tự chuyển kiểu.
    """
    doc = {**DOC_MAC_DINH, **(preset.get("doc") or {})}
    facecam = preset.get("facecam") or {}
    kieu = doc["kieu"]
    canh_bao = None

    if kieu not in ("cam_tren", "khong_cam"):
        canh_bao = f"doc.kieu không hợp lệ ({kieu}), dùng cam_tren"
        kieu = "cam_tren"
    if kieu == "cam_tren" and not all(k in facecam for k in ("x", "y", "w", "h")):
        canh_bao = "preset thiếu toạ độ facecam — chuyển sang kiểu khong_cam"
        kieu = "khong_cam"

    out_w, out_h = _chan(out_w), _chan(out_h)
    sx, sy = src_w / REF_W, src_h / REF_H  # quy đổi toạ độ preset về khung nguồn thật

    if kieu == "khong_cam":
        return {"kieu": kieu, "out_w": out_w, "out_h": out_h, "h_cam": 0, "h_game": out_h,
                "cam": None, "game": (0, 0, _chan(src_w), _chan(src_h)), "canh_bao": canh_bao}

    ti_le = _kep(float(doc["ti_le_cam"]), TI_LE_CAM_MIN, TI_LE_CAM_MAX)
    h_cam = _chan(out_h * ti_le)
    h_game = _chan(out_h - h_cam)
    h_cam = out_h - h_game  # bù phần lẻ do làm tròn để vstack ra đúng out_h

    cam = _cat_trong_khung(facecam["x"] * sx, facecam["y"] * sy,
                           facecam["w"] * sx, facecam["h"] * sy, src_w, src_h)

    # Vùng gameplay: lấy hết chiều cao nguồn, bề rộng theo đúng tỉ lệ khung đích,
    # canh quanh `gameplay_center_x` rồi kẹp lại cho khỏi tràn khung.
    game_w = _chan(min(src_w, src_h * out_w / h_game))
    center = _kep(float(doc["gameplay_center_x"]) * sx, game_w / 2, src_w - game_w / 2)
    game = _cat_trong_khung(center - game_w / 2, 0, game_w, src_h, src_w, src_h)

    return {"kieu": kieu, "out_w": out_w, "out_h": out_h, "h_cam": h_cam, "h_game": h_game,
            "cam": cam, "game": game, "canh_bao": canh_bao}


def _cat_trong_khung(x: float, y: float, w: float, h: float,
                     src_w: int, src_h: int) -> tuple[int, int, int, int]:
    """Kẹp một vùng cắt nằm trọn trong khung nguồn, mọi cạnh chẵn."""
    w = _chan(_kep(w, 2, src_w))
    h = _chan(_kep(h, 2, src_h))
    x = _chan(_kep(x, 0, src_w - w), toi_thieu=0)
    y = _chan(_kep(y, 0, src_h - h), toi_thieu=0)
    return x, y, w, h


def build_vertical_filter(src_w: int, src_h: int, preset: dict, out_w: int = OUT_W,
                          out_h: int = OUT_H, do_mo: int = 20, nhan_ra: str = "v") -> str:
    """Chuỗi filter_complex biến [0:v] thành [<nhan_ra>] khung dọc out_w×out_h."""
    L = compute_vertical_layout(src_w, src_h, preset, out_w, out_h)
    return build_filter_from_layout(L, do_mo, nhan_ra)


def build_filter_from_layout(L: dict, do_mo: int = 20, nhan_ra: str = "v") -> str:
    out_w, out_h = L["out_w"], L["out_h"]
    gx, gy, gw, gh = L["game"]

    if L["kieu"] == "khong_cam":
        # Nền: phóng to lấp đầy khung dọc rồi làm mờ. Trước: gameplay giữ nguyên tỉ lệ, đặt giữa.
        return ";".join([
            "[0:v]split=2[bg][fg]",
            f"[bg]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h},boxblur={do_mo}:2,setsar=1[bgv]",
            f"[fg]scale={out_w}:-2,setsar=1[fgv]",
            f"[bgv][fgv]overlay=(W-w)/2:(H-h)/2[{nhan_ra}]",
        ])

    cx, cy, cw, ch = L["cam"]
    h_cam, h_game = L["h_cam"], L["h_game"]
    return ";".join([
        "[0:v]split=2[cam][game]",
        # Facecam: cắt theo preset, phóng lấp đầy ô rồi cắt giữa (giữ đúng tỉ lệ mặt người).
        f"[cam]crop={cw}:{ch}:{cx}:{cy},scale={out_w}:{h_cam}:force_original_aspect_ratio=increase,"
        f"crop={out_w}:{h_cam},setsar=1[camv]",
        f"[game]crop={gw}:{gh}:{gx}:{gy},scale={out_w}:{h_game},setsar=1[gamev]",
        f"[camv][gamev]vstack=inputs=2[{nhan_ra}]",
    ])
