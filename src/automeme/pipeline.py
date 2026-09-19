"""Nối các bước của pipeline lại với nhau (SPEC §43).

Module này cố tình mỏng: mọi logic nằm trong các hàm thuần được gọi từ đây. Mỗi bước bỏ qua
nếu output đã tồn tại, nên chạy lại từ giữa chừng được (SPEC §49).
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .analyzer.base import StructuredLLM
from .analyzer.context import build_context_windows
from .analyzer.detector import FilterSettings, detect_opportunities, filter_opportunities
from .analyzer.schema import Analysis, load_analysis, save_analysis
from .cache import artifact_status, file_fingerprint, manifest_path, record_artifact, stable_key
from .config import Settings
from .media.audio import extract_audio
from .media.probe import probe
from .memes.base import MemeProvider
from .rendering.filters import build_render_plan, cutaway_style
from .rendering.renderer import render
from .sfx.library import LocalSfxProvider
from .timeline.builder import build_timeline
from .timeline.schema import Timeline, has_asset, load_timeline, save_timeline
from .timeline.validator import resolve_asset, validate_timeline
from .transcription.base import Transcriber
from .transcription.normalize import normalize_transcript, validate_transcript
from .utils.files import PROMPTS_DIR, read_json, write_json
from .utils.logger import log
from .workspace import paths_for, video_fingerprint


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


def analyze_video(video: Path, settings: Settings, *, force: bool = False,
                  llm: StructuredLLM | None = None,
                  prompt_path: Path | None = None) -> tuple[Path, Analysis]:
    """Transcript → analysis.json đã qua schema và ràng buộc cứng.

    `llm` chỉ truyền khi test hoặc tích hợp backend khác; mặc định lấy từ cấu hình.
    """
    video = Path(video).expanduser()
    if not video.exists():
        raise FileNotFoundError(f"Không thấy video: {video}")

    paths = paths_for(video, settings)
    if not paths.transcript.exists():
        raise FileNotFoundError(
            f"Chưa có transcript {paths.transcript}. Chạy `automeme transcribe {video}` trước."
        )

    prompt_file = Path(prompt_path or PROMPTS_DIR / "meme_detector.txt")
    input_key = _analysis_input_key(video, paths.transcript, prompt_file, settings, llm)
    state_file = manifest_path(settings.paths.data_dir, paths.analysis, "analysis")
    status = artifact_status(
        paths.analysis, state_file, stage="analysis", input_key=input_key,
    )
    if not force and status == "fresh":
        log.info("Analysis cache còn mới (%s), bỏ qua LLM.", paths.analysis.name)
        return paths.analysis, load_analysis(paths.analysis)
    if not force and status in {"stale", "modified", "untracked"}:
        log.info("Analysis cache %s; chạy lại bước phân tích.", _status_vi(status))

    transcript = read_json(paths.transcript)
    contexts = build_context_windows(
        transcript,
        previous_count=settings.analyzer.previous_segments,
        next_count=settings.analyzer.next_segments,
    )
    if not contexts:
        raise ValueError("Transcript không có đoạn lời thoại nào để phân tích.")

    from .analyzer.llm import create_llm
    from .analyzer.prompt import load_prompt

    backend = llm or create_llm(settings)
    template = load_prompt(prompt_file)
    raw = detect_opportunities(contexts, backend, template)
    accepted = filter_opportunities(
        raw,
        contexts,
        FilterSettings(
            threshold=settings.editing.threshold,
            cooldown=settings.editing.cooldown,
            max_per_minute=settings.editing.max_memes_per_minute,
            duration_min=settings.meme.duration_min,
            duration_max=settings.meme.duration_max,
            timing_delay=settings.analyzer.timing_delay,
        ),
        video_duration=float(transcript.get("duration") or contexts[-1].end),
    )
    analysis = Analysis(
        video=str(transcript.get("video") or video.name),
        backend=settings.llm.backend,
        model=backend.model,
        opportunities=accepted,
    )
    save_analysis(paths.analysis, analysis)
    record_artifact(
        paths.analysis, state_file, stage="analysis", input_key=input_key,
    )
    log.info("Analysis: giữ %d/%d đề xuất → %s", len(accepted), len(raw), paths.analysis)
    return paths.analysis, analysis


def build_video_timeline(video: Path, settings: Settings, *, force: bool = False,
                         provider: MemeProvider | None = None,
                         sfx_provider: LocalSfxProvider | None = None) -> tuple[Path, Timeline]:
    """analysis.json → tìm/xếp hạng meme và SFX → timeline.json đã kiểm tra."""
    video = Path(video).expanduser()
    if not video.exists():
        raise FileNotFoundError(f"Không thấy video: {video}")
    paths = paths_for(video, settings)
    if not paths.analysis.exists():
        raise FileNotFoundError(
            f"Chưa có analysis {paths.analysis}. Chạy `automeme analyze {video}` trước."
        )

    analysis = load_analysis(paths.analysis)
    input_key = _timeline_input_key(video, paths.analysis, settings, provider)
    state_file = manifest_path(settings.paths.data_dir, paths.timeline, "timeline")
    status = artifact_status(
        paths.timeline, state_file, stage="timeline", input_key=input_key,
    )
    if not force and status == "fresh":
        log.info("Timeline cache còn mới (%s), bỏ qua tìm meme.", paths.timeline.name)
        return paths.timeline, load_timeline(paths.timeline)
    if not force and status in {"modified", "untracked"}:
        log.warning(
            "Timeline %s; coi là bản người dùng chỉnh và giữ nguyên. Dùng --force nếu muốn "
            "sinh lại.", _status_vi(status),
        )
        return paths.timeline, load_timeline(paths.timeline)
    if not force and status == "stale":
        log.info("Timeline cache không còn khớp đầu vào; tìm và xếp hạng lại.")

    from .memes.factory import create_meme_provider

    source = provider or create_meme_provider(settings)
    sound_source = sfx_provider or LocalSfxProvider(
        library_file=settings.sfx.library_file,
        project_root=_goc_du_an(settings),
    )
    info = probe(video)
    timeline = build_timeline(
        analysis,
        source,
        settings.ranking,
        top_k=settings.meme_search.top_k,
        project_root=_goc_du_an(settings),
        video_duration=info.duration,
        sfx_provider=sound_source,
        sfx_settings=settings.sfx,
        cutaway_settings=settings.cutaway,
        meme_settings=settings.meme,
    )
    asset_paths = {
        event.asset: resolve_asset(event.asset, _goc_du_an(settings), settings.paths.assets_dir)
        for event in timeline.events if has_asset(event)
    }
    errors, warnings = validate_timeline(
        timeline,
        video_duration=info.duration,
        asset_paths=asset_paths,
        meme_cfg=settings.meme,
        editing_cfg=settings.editing,
    )
    for warning in warnings:
        log.warning("Timeline tự động: %s", warning)
    if errors:
        raise ValueError("Timeline tự động không hợp lệ:\n" + "\n".join(
            f"  - {error}" for error in errors
        ))
    save_timeline(paths.timeline, timeline)
    record_artifact(
        paths.timeline, state_file, stage="timeline", input_key=input_key,
    )
    meme_count = sum(event.type == "meme" for event in timeline.events)
    sfx_count = sum(event.type == "sfx" for event in timeline.events)
    log.info("Timeline: chọn %d meme + %d SFX từ %d cơ hội → %s", meme_count, sfx_count,
             len(analysis.opportunities), paths.timeline)
    return paths.timeline, timeline


def run_video(video: Path, settings: Settings, *, force: bool = False,
              output: Path | None = None, transcriber: Transcriber | None = None,
              llm: StructuredLLM | None = None,
              provider: MemeProvider | None = None,
              progress_callback: Callable[[str, str], None] | None = None,
              ) -> tuple[Path, Timeline]:
    """Chạy trọn MVP: transcribe → analyze → timeline → render."""
    progress = progress_callback or (lambda _stage, _state: None)
    progress("transcribe", "running")
    transcribe_video(video, settings, force=force, transcriber=transcriber)
    progress("transcribe", "completed")
    progress("analyze", "running")
    analyze_video(video, settings, force=force, llm=llm)
    progress("analyze", "completed")
    progress("timeline", "running")
    timeline_path, _ = build_video_timeline(video, settings, force=force, provider=provider)
    progress("timeline", "completed")
    progress("render", "running")
    result = render_timeline(
        video,
        settings,
        timeline_path=timeline_path,
        output=output,
        force=force,
    )
    progress("render", "completed")
    return result


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
            f"mục 5.4), hoặc chạy `automeme run {video}` để sinh tự động."
        )

    timeline = load_timeline(tl_path)
    thong_tin = probe(video)
    events = timeline.active_events()
    asset_paths = {e.asset: resolve_asset(e.asset, _goc_du_an(settings),
                                          settings.paths.assets_dir)
                   for e in events if has_asset(e)}

    loi, canh_bao = validate_timeline(timeline, video_duration=thong_tin.duration,
                                      asset_paths=asset_paths, meme_cfg=settings.meme,
                                      editing_cfg=settings.editing)
    for c in canh_bao:
        log.warning("Timeline: %s", c)
    if loi:
        raise ValueError("Timeline không hợp lệ:\n" + "\n".join(f"  - {e}" for e in loi))

    out = Path(output) if output else paths.output
    input_key = _render_input_key(video, tl_path, asset_paths, settings)
    state_file = manifest_path(settings.paths.data_dir, out, "render")
    status = artifact_status(out, state_file, stage="render", input_key=input_key)
    if not force and status == "fresh":
        log.info("Video output cache còn mới (%s), bỏ qua render.", out.name)
        return out, timeline
    if not force and status in {"modified", "untracked"}:
        log.warning(
            "Output %s và không được tự ghi đè. Dùng --force hoặc --out sang file khác.",
            _status_vi(status),
        )
        return out, timeline
    if not force and status == "stale":
        log.info("Output cũ do automeme tạo không còn khớp timeline/cấu hình; render lại.")

    plan = build_render_plan(events,
                             [asset_paths[e.asset] if has_asset(e) else None for e in events],
                             video_w=thong_tin.width or 1920, video_h=thong_tin.height or 1080,
                             scale_default=settings.meme.scale_default,
                             position_default=settings.meme.position_default,
                             margin_ratio=settings.meme.margin_ratio,
                             max_height_ratio=settings.meme.max_height_ratio,
                             has_audio=thong_tin.has_audio, fps=thong_tin.fps,
                             style=cutaway_style(settings.cutaway))
    log.info("Render %d sự kiện vào %s...", len(events), video.name)
    render(video, out, plan, video_codec=settings.output.video_codec, crf=settings.output.crf,
           preset=settings.output.preset, audio_codec=settings.output.audio_codec)
    record_artifact(out, state_file, stage="render", input_key=input_key)
    log.info("Xong: %s", out)
    return out, timeline


def _goc_du_an(settings: Settings) -> Path:
    """Thư mục gốc để hiểu đường dẫn tương đối trong timeline ("assets/memes/x.png")."""
    return settings.paths.assets_dir.parent


def _analysis_input_key(video: Path, transcript: Path, prompt: Path, settings: Settings,
                        llm: StructuredLLM | None) -> str:
    if llm is None:
        model = (settings.ollama.model if settings.llm.backend == "ollama"
                 else settings.claude.model)
        backend = settings.llm.backend
    else:
        backend = f"{type(llm).__module__}.{type(llm).__qualname__}"
        model = llm.model
    return stable_key({
        "video": video_fingerprint(video),
        "transcript": file_fingerprint(transcript),
        "prompt": file_fingerprint(prompt),
        "backend": backend,
        "model": model,
        "analyzer": settings.analyzer.model_dump(mode="json"),
        "editing": settings.editing.model_dump(mode="json"),
        "duration": [settings.meme.duration_min, settings.meme.duration_max],
    })


def _timeline_input_key(video: Path, analysis: Path, settings: Settings,
                        provider: MemeProvider | None) -> str:
    provider_name = "configured" if provider is None else (
        f"{type(provider).__module__}.{type(provider).__qualname__}"
    )
    token_key = stable_key(settings.meme_search.token) if settings.meme_search.token else ""
    return stable_key({
        "video": video_fingerprint(video),
        "analysis": file_fingerprint(analysis),
        "provider": provider_name,
        "meme_search": {
            "base_url": settings.meme_search.base_url,
            "token_key": token_key,
            "top_k": settings.meme_search.top_k,
        },
        "library": _file_identity(settings.meme.library_file),
        "assets": _asset_index(settings),
        "ranking": settings.ranking.model_dump(mode="json"),
        "sfx": settings.sfx.model_dump(mode="json"),
        "sfx_library": _file_identity(settings.sfx.library_file),
        # đổi cách dựng (tràn màn hình, zoom, style bị loại, vị trí) thì phải dựng lại timeline
        "cutaway": settings.cutaway.model_dump(mode="json"),
        "meme": settings.meme.model_dump(mode="json", include={
            "duration_min", "duration_max", "exclude_styles", "position_cycle"}),
    })


def _render_input_key(video: Path, timeline: Path, asset_paths: dict[str, Path],
                      settings: Settings) -> str:
    return stable_key({
        "video": video_fingerprint(video),
        "timeline": file_fingerprint(timeline),
        "assets": {
            name: _file_identity(path) for name, path in sorted(asset_paths.items())
        },
        "meme": {
            "scale_default": settings.meme.scale_default,
            "position_default": settings.meme.position_default,
            "margin_ratio": settings.meme.margin_ratio,
        },
        "output": settings.output.model_dump(mode="json"),
    })


def _file_identity(path: Path) -> str | None:
    path = Path(path)
    return file_fingerprint(path) if path.is_file() else None


def _asset_index(settings: Settings) -> list[tuple[str, int, int]]:
    root = _goc_du_an(settings)
    rows = []
    for directory in (
        settings.paths.assets_dir / "memes",
        settings.paths.assets_dir / "gifs",
        settings.paths.assets_dir / "sfx",
    ):
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            stat = path.stat()
            try:
                name = path.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                name = str(path.resolve())
            rows.append((name, stat.st_size, stat.st_mtime_ns))
    return rows


def _status_vi(status: str) -> str:
    return {
        "modified": "đã bị sửa ngoài automeme",
        "untracked": "có từ phiên bản cũ hoặc không có manifest",
        "stale": "không còn khớp đầu vào",
    }.get(status, status)
