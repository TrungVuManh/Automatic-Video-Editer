"""Tách audio cho Whisper: WAV PCM 16-bit, mono, 16 kHz (SPEC §15)."""
from __future__ import annotations

from pathlib import Path

from ..utils.logger import log
from .ffmpeg import require_binary, run_cmd

# Định dạng đầu vào Whisper yêu cầu — đặc tả của model, không phải tham số tinh chỉnh
SAMPLE_RATE = 16_000
CHANNELS = 1


def build_extract_audio_cmd(video: Path, audio: Path, ffmpeg: str = "ffmpeg") -> list[str]:
    """Hàm thuần: lệnh FFmpeg tách audio."""
    return [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(video),
        "-vn", "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le",
        str(audio),
    ]


def extract_audio(video: Path, audio: Path, *, force: bool = False) -> Path:
    """Tách audio; bỏ qua nếu file đã có (trừ khi `force`).

    FFmpeg ghi ra file tạm rồi mới đổi tên, nên nếu bị ngắt giữa chừng sẽ không để lại
    một file dở dang bị tưởng là đã xong.
    """
    if audio.exists() and not force:
        log.info("Đã có %s, bỏ qua bước tách audio.", audio.name)
        return audio
    if not video.exists():
        raise FileNotFoundError(f"Không thấy video: {video}")

    exe = require_binary("ffmpeg")
    audio.parent.mkdir(parents=True, exist_ok=True)
    tmp = audio.with_name(f"{audio.stem}.part{audio.suffix}")  # giữ đuôi để FFmpeg nhận định dạng
    log.info("Tách audio: %s → %s", video.name, audio.name)
    try:
        run_cmd(build_extract_audio_cmd(video, tmp, ffmpeg=exe))
        tmp.replace(audio)
    finally:
        tmp.unlink(missing_ok=True)
    return audio
