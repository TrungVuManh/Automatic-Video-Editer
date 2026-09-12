"""Gọi FFmpeg để render timeline vào video (SPEC §40).

Phần dựng lệnh là hàm thuần (`build_ffmpeg_cmd`), phần chạy chỉ là lớp mỏng. Audio gốc được
copy nguyên vẹn (SPEC §61); chỉ khi container không nhận mới encode lại theo `output.audio_codec`.
"""
from __future__ import annotations

from pathlib import Path

from ..media.ffmpeg import CommandError, require_binary, run_cmd
from ..utils.logger import log
from .filters import RenderPlan


def build_ffmpeg_cmd(video: Path, output: Path, plan: RenderPlan, *, video_codec: str, crf: int,
                     preset: str, audio_codec: str | None = None,
                     ffmpeg: str = "ffmpeg") -> list[str]:
    """`audio_codec=None` nghĩa là copy nguyên audio gốc."""
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(video)]
    cmd += plan.input_args
    if plan.filter_complex:
        cmd += ["-filter_complex", plan.filter_complex]
    cmd += ["-map", plan.out_label or "0:v"]
    cmd += ["-map", plan.out_audio_label or "0:a?"]
    if plan.out_audio_label:
        cmd += ["-c:a", audio_codec or "aac"]
    else:
        cmd += ["-c:a", "copy"] if audio_codec is None else ["-c:a", audio_codec]
    cmd += ["-c:v", video_codec, "-crf", str(crf), "-preset", preset,
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
    return cmd


def render(video: Path, output: Path, plan: RenderPlan, *, video_codec: str, crf: int,
           preset: str, audio_codec: str) -> Path:
    """Ghi ra file tạm rồi đổi tên, để lần chạy hỏng không để lại video dở dang."""
    exe = require_binary("ffmpeg")
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(f"{output.stem}.part{output.suffix}")
    try:
        try:
            if plan.out_audio_label:
                run_cmd(build_ffmpeg_cmd(video, tmp, plan, video_codec=video_codec, crf=crf,
                                         preset=preset, audio_codec=audio_codec, ffmpeg=exe))
                tmp.replace(output)
                return output
            run_cmd(build_ffmpeg_cmd(video, tmp, plan, video_codec=video_codec, crf=crf,
                                     preset=preset, audio_codec=None, ffmpeg=exe))
        except CommandError as e:
            # Audio gốc không copy được vào MP4 (ví dụ nguồn là Opus trong WebM) → encode lại
            log.warning("Không copy được audio gốc, encode lại bằng %s. Chi tiết: %s",
                        audio_codec, str(e).splitlines()[-1][:200])
            run_cmd(build_ffmpeg_cmd(video, tmp, plan, video_codec=video_codec, crf=crf,
                                     preset=preset, audio_codec=audio_codec, ffmpeg=exe))
        tmp.replace(output)
    finally:
        tmp.unlink(missing_ok=True)
    return output
