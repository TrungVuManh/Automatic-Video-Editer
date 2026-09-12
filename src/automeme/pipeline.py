"""Nối các bước của pipeline lại với nhau (SPEC §43).

Module này cố tình mỏng: mọi logic nằm trong các hàm thuần được gọi từ đây. Mỗi bước bỏ qua
nếu output đã tồn tại, nên chạy lại từ giữa chừng được (SPEC §49).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Settings
from .media.audio import extract_audio
from .media.probe import probe
from .rendering.filters import build_render_plan
from .rendering.renderer import render
from .timeline.schema import Timeline, load_timeline
from .timeline.validator import resolve_asset, validate_timeline
from .transcription.base import Transcriber
from .transcription.normalize import normalize_transcript, validate_transcript
from .utils.files import read_json, write_json
from .utils.logger import log
from .workspace import paths_for


def transcribe_video(video: Path, settings: Settings, *, force: bool = False,
                     transcriber: Transcriber | None = None) -> tuple[Path, dict[str, Any]]:
    """Video → audio → transcript đã chuẩn hóa. Trả về (đường dẫn transcript, dữ liệu).

    `transcriber` chỉ dùng khi test; để trống thì dùng faster-whisper theo cấu hình.
    """
    video = Path(video).expanduser()
    if not video.exists():
        raise FileNotFoundError(f"Không thấy video: {video}")

    paths = paths_for(video, settings)
    if paths.transcript_cache.exists() and not force:
        log.info("Đã có transcript trong cache (%s), bỏ qua nhận dạng. Thêm --force để "
                 "làm lại.", paths.transcript_cache.name)
        data = read_json(paths.transcript_cache)
    else:
        extract_audio(video, paths.audio, force=force)
        thong_tin = probe(video)
        tu_tao = transcriber is None
        if transcriber is None:
            from .transcription.whisper import FasterWhisperTranscriber
            transcriber = FasterWhisperTranscriber(settings.whisper)
        try:
            raw = transcriber.transcribe(paths.audio)
        finally:
            if tu_tao:
                transcriber.unload()  # trả VRAM ngay, bước sau còn cần
        data = normalize_transcript(raw, video_name=video.name,
                                    model=settings.whisper.model,
                                    duration=thong_tin.duration)
        write_json(paths.transcript_cache, data)

    for canh_bao in validate_transcript(data):
        log.warning("Transcript: %s", canh_bao)
    write_json(paths.transcript, data)
    log.info("Transcript: %d đoạn, %d từ → %s",
             len(data["segments"]), len(data["words"]), paths.transcript)
    return paths.transcript, data


def render_timeline(video: Path, settings: Settings, *, timeline_path: Path | None = None,
                    output: Path | None = None, force: bool = False) -> tuple[Path, Timeline]:
    """Video + timeline.json → video đã chèn meme. Trả về (đường dẫn output, timeline).

    Không hợp lệ thì dừng hẳn với danh sách lỗi — không render ra thứ sai rồi mới báo.
    """
    video = Path(video).expanduser()
    if not video.exists():
        raise FileNotFoundError(f"Không thấy video: {video}")

    paths = paths_for(video, settings)
    tl_path = Path(timeline_path) if timeline_path else paths.timeline
    if not tl_path.exists():
        raise FileNotFoundError(
            f"Chưa có timeline {tl_path}. Tự viết một file timeline.json (xem docs/GUIDE.md "
            f"mục 5.4), hoặc chờ lệnh `analyze` ở Iteration 3."
        )

    timeline = load_timeline(tl_path)
    thong_tin = probe(video)
    events = timeline.sorted_events()
    asset_paths = {e.asset: resolve_asset(e.asset, _goc_du_an(settings),
                                          settings.paths.assets_dir) for e in events}

    loi, canh_bao = validate_timeline(timeline, video_duration=thong_tin.duration,
                                      asset_paths=asset_paths, meme_cfg=settings.meme,
                                      editing_cfg=settings.editing)
    for c in canh_bao:
        log.warning("Timeline: %s", c)
    if loi:
        raise ValueError("Timeline không hợp lệ:\n" + "\n".join(f"  - {e}" for e in loi))

    out = Path(output) if output else paths.output
    if out.exists() and not force:
        log.info("Đã có %s, bỏ qua render. Thêm --force để làm lại.", out.name)
        return out, timeline

    plan = build_render_plan(events, [asset_paths[e.asset] for e in events],
                             video_w=thong_tin.width or 1920, video_h=thong_tin.height or 1080,
                             scale_default=settings.meme.scale_default,
                             position_default=settings.meme.position_default,
                             margin_ratio=settings.meme.margin_ratio)
    log.info("Render %d meme vào %s...", len(events), video.name)
    render(video, out, plan, video_codec=settings.output.video_codec, crf=settings.output.crf,
           preset=settings.output.preset, audio_codec=settings.output.audio_codec)
    log.info("Xong: %s", out)
    return out, timeline


def _goc_du_an(settings: Settings) -> Path:
    """Thư mục gốc để hiểu đường dẫn tương đối trong timeline ("assets/memes/x.png")."""
    return settings.paths.assets_dir.parent
