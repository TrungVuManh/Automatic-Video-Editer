"""Bước 1 — Thu thập: tải VOD + chat replay, tách audio mono 16 kHz."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .common import Job, log, require_binary, run_cmd


def fetch(job: Job) -> None:
    _get_video(job)
    _get_chat(job)
    extract_audio(job.video, job.audio)
    log.info("Bước 1 xong: %s", job.dir)


def _get_video(job: Job) -> None:
    if job.video.exists():
        log.info("Đã có video, bỏ qua tải.")
        return
    if job.local_video:
        log.info("Dùng video có sẵn: %s", job.local_video)
        shutil.copy(job.local_video, job.video)
        return
    if not job.url:
        raise ValueError("Cần --url hoặc --video.")
    require_binary("yt-dlp")
    log.info("Đang tải VOD (có thể mất khá lâu)...")
    run_cmd([
        "yt-dlp", "-f", "bv*[height<=1080]+ba/b[height<=1080]",
        "--merge-output-format", "mp4",
        "-o", str(job.video), job.url,
    ])


def _get_chat(job: Job) -> None:
    if job.chat_raw.exists():
        return
    if job.local_chat:
        shutil.copy(job.local_chat, job.chat_raw)
        return
    if not job.url:
        log.warning("Không có URL và không có file chat — bước 3 sẽ chỉ dùng âm lượng + từ khóa.")
        return

    try:
        if job.platform == "youtube":
            _youtube_chat(job)
        elif job.platform == "twitch":
            _twitch_chat(job)
        else:
            raise ValueError(f"Nền tảng không hỗ trợ: {job.platform}")
    except Exception as e:  # chat là tín hiệu phụ, không để hỏng cả pipeline
        log.warning("Không tải được chat (%s). Tiếp tục không có chat.", e)


def _youtube_chat(job: Job) -> None:
    require_binary("yt-dlp")
    stem = job.chat_raw.with_suffix("")  # yt-dlp tự thêm .live_chat.json
    run_cmd([
        "yt-dlp", "--skip-download", "--write-subs", "--sub-langs", "live_chat",
        "-o", str(stem), job.url,
    ])
    produced = stem.parent / f"{stem.name}.live_chat.json"
    if not produced.exists():
        raise FileNotFoundError("VOD này không có live chat replay.")
    produced.rename(job.chat_raw)


def _twitch_chat(job: Job) -> None:
    exe = require_binary("TwitchDownloaderCLI")
    m = re.search(r"videos/(\d+)", job.url or "")
    if not m:
        raise ValueError("URL Twitch phải có dạng https://www.twitch.tv/videos/<id>")
    run_cmd([exe, "chatdownload", "--id", m.group(1), "-o", str(job.chat_raw)])


def extract_audio(video: Path, audio: Path) -> None:
    if audio.exists():
        return
    require_binary("ffmpeg")
    log.info("Tách audio...")
    run_cmd(["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
             "-c:a", "pcm_s16le", str(audio)])
