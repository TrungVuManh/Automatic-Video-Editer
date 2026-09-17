"""Kiểm tra timeline trước khi render (SPEC §54).

Đây là chỗ **code** giữ kỷ luật thay cho LLM (SPEC §53): thời điểm hợp lệ, file tồn tại, không
chồng lấn bậy, không quá dày. Toàn bộ là hàm thuần — không đọc gì ngoài việc hỏi file có tồn
tại hay không, và việc đó được đưa vào tham số `ton_tai` để test không cần tạo file thật.

Trả về hai danh sách:
- **lỗi**: chặn render (render sẽ hỏng hoặc sai hẳn);
- **cảnh báo**: vẫn render được nhưng nên xem lại (meme dày quá, dài quá…).
"""
from __future__ import annotations

import math
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
            kind = "meme" if isinstance(e, MemeEvent) else "SFX"
            loi.append(f"{e.id}: không thấy file {kind} {e.asset}")

        if isinstance(e, MemeEvent):
            scale = e.scale
            if scale is not None and not (SCALE_MIN <= scale <= SCALE_MAX):
                loi.append(f"{e.id}: scale {scale} ngoài khoảng {SCALE_MIN}–{SCALE_MAX}")

        if meme_cfg is not None and isinstance(e, MemeEvent):
            if e.duration < meme_cfg.duration_min:
                canh_bao.append(f"{e.id}: dài {e.duration:.2f}s, ngắn hơn mức tối thiểu "
                                f"{meme_cfg.duration_min}s trong cấu hình")
            if e.duration > meme_cfg.duration_max:
                canh_bao.append(f"{e.id}: dài {e.duration:.2f}s, vượt mức tối đa "
                                f"{meme_cfg.duration_max}s trong cấu hình")

    meme_events = [event for event in events if isinstance(event, MemeEvent)]
    loi += _kiem_tra_chong_lan(meme_events)
    if editing_cfg is not None:
        canh_bao += _kiem_tra_mat_do(meme_events, video_duration, editing_cfg)
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
        # Đo từ lúc meme trước BẮT ĐẦU, giống SPEC §32 ("00:05 meme → 00:13 được giữ" với
        # cooldown 7s) và giống bộ lọc của analyzer/builder. Đo từ lúc kết thúc thì timeline do
        # chính hệ thống dựng bị báo vi phạm.
        cach = b.start - a.start
        if cach < cfg.cooldown:
            canh_bao.append(f"{a.id} → {b.id} bắt đầu cách nhau {cach:.1f}s, dưới cooldown "
                            f"{cfg.cooldown}s")
    if video_duration and video_duration > 0:
        # Cùng công thức với analyzer/detector.py: video ngắn vẫn được ít nhất 1 meme. Chia thẳng
        # số meme cho thời lượng thì 1 meme trong video 12 giây đã thành "5 meme/phút".
        toi_da = max(1, math.floor(video_duration * cfg.max_memes_per_minute / 60))
        if len(events) > toi_da:
            canh_bao.append(f"{len(events)} meme, vượt mức {toi_da} cho video dài "
                            f"{format_ts(video_duration)} ({cfg.max_memes_per_minute} "
                            f"meme/phút trong cấu hình)")
    return canh_bao


def format_timeline_table(timeline: Timeline, loi: list[str], canh_bao: list[str],
                          video_duration: float | None = None) -> str:
    """Bảng cho lệnh `automeme inspect`."""
    events = timeline.sorted_events()
    active_count = len(timeline.active_events())
    dai_video = f", video {format_ts(video_duration)}" if video_duration else ""
    dong = ["", f"TIMELINE  {timeline.video}  ({active_count} sự kiện bật / "
            f"{len(events)} tổng{dai_video})"]
    head = (f"  {'mã':<12} {'loại':<5} {'trạng thái':<10} {'bắt đầu':>9} {'dài':>6}  "
            f"{'hiển thị/âm lượng':<20} asset")
    dong += [head, "  " + "-" * (len(head) - 2)]
    for e in events:
        if isinstance(e, MemeEvent):
            co = f"{e.scale * 100:.0f}%" if e.scale is not None else "mặc"
            detail = f"{e.position or 'mặc định'} {co}"
        else:
            detail = f"volume {e.volume:.0%}"
        dong.append(
            f"  {e.id:<12} {e.type:<5} {e.status:<10} {format_ts(e.start):>9} "
            f"{e.duration:>6.2f}  {detail:<20} {e.asset}"
        )
    if not events:
        dong.append("  (chưa có sự kiện nào)")
    for c in canh_bao:
        dong.append(f"  [cảnh báo] {c}")
    for e in loi:
        dong.append(f"  [LỖI]      {e}")
    dong.append("  → " + ("có lỗi, chưa render được." if loi else "hợp lệ, render được."))
    return "\n".join(dong)
