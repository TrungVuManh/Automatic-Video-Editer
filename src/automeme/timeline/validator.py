"""Kiểm tra timeline trước khi render (SPEC §54).

Đây là chỗ **code** giữ kỷ luật thay cho LLM (SPEC §53): thời điểm hợp lệ, file tồn tại, không
chồng lấn bậy, không quá dày. Toàn bộ là hàm thuần — không đọc gì ngoài việc hỏi file có tồn
tại hay không, và việc đó được đưa vào tham số `ton_tai` để test không cần tạo file thật.

Trả về hai danh sách:
- **lỗi**: chặn render (render sẽ hỏng hoặc sai hẳn);
- **cảnh báo**: vẫn render được nhưng nên xem lại (meme dày quá, dài quá…).
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..utils.timestamps import format_ts
from .schema import SCALE_MAX, SCALE_MIN, MemeEvent, Timeline

# Sai lệch cho phép khi so thời điểm kết thúc với thời lượng video (giây)
DUNG_SAI = 0.05


def resolve_asset(asset: str, base_dir: Path, assets_dir: Path) -> Path:
    """Đường dẫn asset trong timeline → đường dẫn thật.

    Đường dẫn tuyệt đối giữ nguyên; tương đối thử lần lượt từ thư mục gốc dự án
    ("assets/memes/x.png") rồi từ thư mục assets ("memes/x.png").
    """
    p = Path(asset).expanduser()
    if p.is_absolute():
        return p
    ung_vien = [base_dir / p, assets_dir / p]
    for duong_dan in ung_vien:
        if duong_dan.exists():
            return duong_dan
    return ung_vien[0]


def validate_timeline(timeline: Timeline, *, video_duration: float | None,
                      asset_paths: dict[str, Path], meme_cfg=None, editing_cfg=None,
                      ton_tai: Callable[[Path], bool] = Path.exists) -> tuple[list[str], list[str]]:
    """`asset_paths` là {asset trong timeline → đường dẫn thật} (xem `resolve_asset`)."""
    loi: list[str] = []
    canh_bao: list[str] = []
    all_events = timeline.sorted_events()
    events = timeline.active_events()

    ma_da_gap: set[str] = set()
    for e in all_events:
        if e.id in ma_da_gap:
            loi.append(f"trùng mã sự kiện: {e.id}")
        ma_da_gap.add(e.id)

    for e in events:

        if video_duration is not None and e.end > video_duration + DUNG_SAI:
            loi.append(f"{e.id}: kết thúc ở {format_ts(e.end)} nhưng video chỉ dài "
                       f"{format_ts(video_duration)}")
        duong_dan = asset_paths.get(e.asset)
        if duong_dan is None or not ton_tai(duong_dan):
            loi.append(f"{e.id}: không thấy file meme {e.asset}")

        scale = e.scale
        if scale is not None and not (SCALE_MIN <= scale <= SCALE_MAX):
            loi.append(f"{e.id}: scale {scale} ngoài khoảng {SCALE_MIN}–{SCALE_MAX}")

        if meme_cfg is not None:
            if e.duration < meme_cfg.duration_min:
                canh_bao.append(f"{e.id}: dài {e.duration:.2f}s, ngắn hơn mức tối thiểu "
                                f"{meme_cfg.duration_min}s trong cấu hình")
            if e.duration > meme_cfg.duration_max:
                canh_bao.append(f"{e.id}: dài {e.duration:.2f}s, vượt mức tối đa "
                                f"{meme_cfg.duration_max}s trong cấu hình")

    loi += _kiem_tra_chong_lan(events)
    if editing_cfg is not None:
        canh_bao += _kiem_tra_mat_do(events, video_duration, editing_cfg)
    return loi, canh_bao


def _kiem_tra_chong_lan(events: list[MemeEvent]) -> list[str]:
    """Hai meme cùng vị trí mà trùng thời gian sẽ đè lên nhau — không render ra cái gì xem được."""
    loi = []
    for i, a in enumerate(events):
        for b in events[i + 1:]:
            if b.start >= a.end:
                break  # events đã sắp xếp theo start
            if (a.position or "") == (b.position or ""):
                loi.append(f"{a.id} và {b.id} cùng vị trí và trùng thời gian "
                           f"({format_ts(b.start)} → {format_ts(a.end)})")
    return loi


def _kiem_tra_mat_do(events: list[MemeEvent], video_duration: float | None, cfg) -> list[str]:
    """Cooldown (SPEC §32) và số meme mỗi phút (SPEC §33) — vi phạm thì chỉ cảnh báo, vì
    timeline viết tay là quyền của người dùng."""
    canh_bao = []
    for a, b in zip(events, events[1:], strict=False):
        cach = b.start - a.end
        if cach < cfg.cooldown:
            canh_bao.append(f"{a.id} → {b.id} chỉ cách {cach:.1f}s, dưới cooldown "
                            f"{cfg.cooldown}s")
    if video_duration and video_duration > 0:
        mat_do = len(events) / (video_duration / 60)
        if mat_do > cfg.max_memes_per_minute:
            canh_bao.append(f"mật độ {mat_do:.1f} meme/phút, vượt mức "
                            f"{cfg.max_memes_per_minute} trong cấu hình")
    return canh_bao


def format_timeline_table(timeline: Timeline, loi: list[str], canh_bao: list[str],
                          video_duration: float | None = None) -> str:
    """Bảng cho lệnh `automeme inspect`."""
    events = timeline.sorted_events()
    active_count = len(timeline.active_events())
    dai_video = f", video {format_ts(video_duration)}" if video_duration else ""
    dong = ["", f"TIMELINE  {timeline.video}  ({active_count} sự kiện bật / "
            f"{len(events)} tổng{dai_video})"]
    head = (f"  {'mã':<12} {'trạng thái':<10} {'bắt đầu':>9} {'dài':>6}  "
            f"{'vị trí':<13} {'cỡ':>5}  asset")
    dong += [head, "  " + "-" * (len(head) - 2)]
    for e in events:
        co = f"{e.scale * 100:.0f}%" if e.scale is not None else "mặc"
        dong.append(f"  {e.id:<12} {e.status:<10} {format_ts(e.start):>9} {e.duration:>6.2f}  "
                    f"{(e.position or 'mặc định'):<13} {co:>5}  {e.asset}")
    if not events:
        dong.append("  (chưa có sự kiện nào)")
    for c in canh_bao:
        dong.append(f"  [cảnh báo] {c}")
    for e in loi:
        dong.append(f"  [LỖI]      {e}")
    dong.append("  → " + ("có lỗi, chưa render được." if loi else "hợp lệ, render được."))
    return "\n".join(dong)
