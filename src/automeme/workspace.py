"""Đường dẫn output của một video và khóa cache (SPEC §48).

Cache phụ thuộc nội dung video *và* tham số ASR, nên khi đổi model hoặc ngôn ngữ, lần chạy
sau tạo file mới thay vì lặng lẽ dùng lại transcript cũ.

    data/cache/<ten-video>-<hash8>/audio.wav
    data/cache/<ten-video>-<hash8>/transcript-<asr8>.json
    data/transcripts/<ten-video>.json        ← bản mới nhất, các bước sau đọc file này
    data/analysis/<ten-video>.json           ← cơ hội meme sau khi lọc
    data/timelines/<ten-video>.timeline.json ← bản dựng, người sửa được
    data/output/<ten-video>_automeme.mp4     ← video hoàn chỉnh
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .config import Settings, WhisperSettings

KHOI = 1024 * 1024  # số byte đọc ở đầu và ở cuối video khi lấy vân tay


@dataclass(frozen=True)
class VideoPaths:
    video: Path
    cache_dir: Path
    audio: Path
    transcript_cache: Path
    transcript: Path
    analysis: Path
    timeline: Path
    output: Path


def paths_for(video: Path, settings: Settings) -> VideoPaths:
    data_dir = settings.paths.data_dir
    ten = slug(video.stem)
    cache_dir = data_dir / "cache" / f"{ten}-{video_fingerprint(video)}"
    return VideoPaths(
        video=video,
        cache_dir=cache_dir,
        audio=cache_dir / "audio.wav",
        transcript_cache=cache_dir / f"transcript-{asr_key(settings.whisper)}.json",
        transcript=data_dir / "transcripts" / f"{ten}.json",
        analysis=data_dir / "analysis" / f"{ten}.json",
        timeline=data_dir / "timelines" / f"{ten}.timeline.json",
        output=data_dir / "output" / f"{ten}_automeme.mp4",
    )


def video_fingerprint(video: Path, length: int = 8) -> str:
    """Vân tay nội dung video: kích thước + 1 MB đầu + 1 MB cuối.

    Không băm cả file vì video vài GB sẽ mất hàng chục giây. Đổi lại, hai file cùng kích
    thước mà chỉ khác nhau ở khúc giữa sẽ ra cùng vân tay — hiếm trong thực tế, và khi đó
    vẫn chạy lại được bằng `--force`.
    """
    h = hashlib.sha256()
    size = video.stat().st_size
    h.update(str(size).encode())
    with open(video, "rb") as f:
        h.update(f.read(KHOI))
        if size > KHOI:
            f.seek(max(0, size - KHOI))
            h.update(f.read(KHOI))
    return h.hexdigest()[:length]


def asr_key(cfg: WhisperSettings, length: int = 8) -> str:
    """Khóa của những tham số ASR làm thay đổi kết quả nhận dạng."""
    phan = "|".join([
        cfg.model, cfg.language, cfg.compute_type, str(cfg.beam_size),
        str(cfg.vad_filter), str(cfg.condition_on_previous_text),
    ])
    return hashlib.sha256(phan.encode()).hexdigest()[:length]


def slug(text: str, max_len: int = 60) -> str:
    """Tên file an toàn: bỏ dấu tiếng Việt, đổi ký tự lạ thành '-'."""
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-._")
    return text[:max_len].lower() or "video"
