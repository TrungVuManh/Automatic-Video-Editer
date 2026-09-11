"""Đọc thông tin media (thời lượng, kích thước, fps, audio) bằng ffprobe."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ffmpeg import CommandError, require_binary, run_cmd


@dataclass(frozen=True)
class MediaInfo:
    duration: float | None           # giây; None với ảnh tĩnh hoặc khi ffprobe không biết
    width: int | None
    height: int | None
    fps: float | None
    has_video: bool
    has_audio: bool
    audio_sample_rate: int | None
    audio_channels: int | None
    format_name: str                 # "mov,mp4,m4a,3gp,3g2,mj2", "gif", "png_pipe"…


def probe(path: Path) -> MediaInfo:
    exe = require_binary("ffprobe")
    out = run_cmd([exe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)])
    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        raise CommandError(f"ffprobe trả về dữ liệu không đọc được cho {path}: {e}") from e
    return parse_probe(data)


def parse_probe(data: dict[str, Any]) -> MediaInfo:
    """Hàm thuần: JSON của `ffprobe -show_format -show_streams -of json` → MediaInfo."""
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    # Bỏ qua ảnh bìa (attached_pic) — nó cũng được ffprobe báo là luồng video
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not (s.get("disposition") or {}).get("attached_pic")), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration = _to_float(fmt.get("duration"))
    if duration is None:
        durations = [d for s in streams if (d := _to_float(s.get("duration"))) is not None]
        duration = max(durations) if durations else None

    fps = None
    if video:
        fps = _parse_rate(video.get("avg_frame_rate")) or _parse_rate(video.get("r_frame_rate"))

    return MediaInfo(
        duration=duration,
        width=_to_int(video.get("width")) if video else None,
        height=_to_int(video.get("height")) if video else None,
        fps=fps,
        has_video=video is not None,
        has_audio=audio is not None,
        audio_sample_rate=_to_int(audio.get("sample_rate")) if audio else None,
        audio_channels=_to_int(audio.get("channels")) if audio else None,
        format_name=str(fmt.get("format_name", "")),
    )


def _to_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None  # thiếu, hoặc "N/A"
    return f if f >= 0 else None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_rate(value: Any) -> float | None:
    """'30000/1001' → 29.97; '0/0' hoặc thiếu → None."""
    if not value:
        return None
    num, _, den = str(value).partition("/")
    try:
        n, d = float(num), float(den or 1)
    except ValueError:
        return None
    if n <= 0 or d <= 0:
        return None
    return round(n / d, 3)
