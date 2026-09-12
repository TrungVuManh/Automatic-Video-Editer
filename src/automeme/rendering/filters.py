r"""Dựng filter_complex cho FFmpeg — hàm thuần, không gọi FFmpeg (SPEC §40).

Mỗi meme là một input riêng (`-i`), nên đường dẫn **không bao giờ** nằm trong chuỗi filter —
tránh hẳn chuyện escape `:` và `\` trên Windows.

Mỗi sự kiện sinh ra hai đoạn filter:

    [1:v]scale=576:-2,setpts=PTS-STARTPTS+8.880/TB[m0]
    [0:v][m0]overlay=W-w-58:H-h-58:enable='between(t,8.880,10.230)':eof_action=pass[v]

- `scale`: bề rộng = tỉ lệ `scale` của bề rộng video (SPEC §38), cao `-2` để giữ tỉ lệ và luôn chẵn.
- `setpts`: dời meme tới đúng thời điểm, để GIF bắt đầu chạy từ khung đầu.
- `enable`: chỉ hiện trong khoảng của sự kiện; `eof_action=pass` để video chính không bị cắt
  ngắn khi meme hết.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ..timeline.schema import MemeEvent

# Đuôi file được coi là ảnh động (phải cho lặp) và ảnh tĩnh (phải giữ một khung hình)
DUOI_ANH_DONG = {".gif", ".webp", ".apng"}
DUOI_VIDEO = {".mp4", ".mov", ".mkv", ".webm"}


@dataclass(frozen=True)
class RenderPlan:
    input_args: list[str]   # tham số -i của các meme, theo đúng thứ tự sự kiện
    filter_complex: str     # rỗng nếu không có sự kiện nào
    out_label: str          # nhãn luồng video ra, ví dụ "[v]"; rỗng khi không lọc gì


def build_render_plan(events: Sequence[MemeEvent], asset_paths: Sequence[Path], *,
                      video_w: int, video_h: int, scale_default: float,
                      position_default: str, margin_ratio: float) -> RenderPlan:
    """Sự kiện + đường dẫn meme → tham số input và filter_complex."""
    if len(events) != len(asset_paths):
        raise ValueError("Số sự kiện và số đường dẫn asset không khớp")
    if not events:
        return RenderPlan(input_args=[], filter_complex="", out_label="")

    le = max(0, round(video_w * margin_ratio))
    input_args: list[str] = []
    chuan_bi: list[str] = []
    chuoi_overlay: list[str] = []
    nhan_truoc = "[0:v]"

    for i, (e, asset) in enumerate(zip(events, asset_paths, strict=True)):
        input_args += input_cho_meme(asset, e.duration)
        rong = _chan(video_w * (e.scale if e.scale is not None else scale_default))
        chuan_bi.append(f"[{i + 1}:v]scale={rong}:-2,setpts=PTS-STARTPTS+{e.start:.3f}/TB[m{i}]")

        x, y = vi_tri_overlay(e.position or position_default, le)
        nhan_sau = "[v]" if i == len(events) - 1 else f"[v{i}]"
        chuoi_overlay.append(
            f"{nhan_truoc}[m{i}]overlay={x}:{y}:"
            f"enable='between(t,{e.start:.3f},{e.end:.3f})':eof_action=pass{nhan_sau}"
        )
        nhan_truoc = nhan_sau

    return RenderPlan(input_args=input_args,
                      filter_complex=";".join(chuan_bi + chuoi_overlay),
                      out_label="[v]")


def input_cho_meme(asset: Path, duration: float) -> list[str]:
    """Tham số `-i` tùy loại meme.

    Ảnh tĩnh phải `-loop 1` (nếu không chỉ có đúng một khung hình), ảnh động phải
    `-ignore_loop 0` để lặp hết thời lượng sự kiện. `-t` cắt input cho khỏi kéo dài vô tận.
    """
    duoi = asset.suffix.lower()
    thoi_luong = f"{duration:.3f}"
    if duoi in DUOI_ANH_DONG:
        return ["-ignore_loop", "0", "-t", thoi_luong, "-i", str(asset)]
    if duoi in DUOI_VIDEO:
        return ["-stream_loop", "-1", "-t", thoi_luong, "-i", str(asset)]
    return ["-loop", "1", "-t", thoi_luong, "-i", str(asset)]


def vi_tri_overlay(position: str, le: int) -> tuple[str, str]:
    """Vị trí → biểu thức x, y cho overlay (SPEC §37).

    Dùng biến W/H (khung nền) và w/h (meme) của FFmpeg nên không cần biết trước cỡ meme.
    """
    bang = {
        "top-left": (f"{le}", f"{le}"),
        "top-right": (f"W-w-{le}", f"{le}"),
        "bottom-left": (f"{le}", f"H-h-{le}"),
        "bottom-right": (f"W-w-{le}", f"H-h-{le}"),
        "center": ("(W-w)/2", "(H-h)/2"),
    }
    if position not in bang:
        raise ValueError(f"Vị trí không hợp lệ: {position!r}")
    return bang[position]


def _chan(n: float) -> int:
    """Làm tròn xuống số chẵn — libx264 yêu cầu cạnh chẵn."""
    return max(2, int(n // 2) * 2)
