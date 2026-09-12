"""CLI `automeme` (Typer) — SPEC §44–45.

Lệnh chưa làm sẽ báo rõ thuộc iteration nào trong docs/HANDOFF.md và thoát với mã 1.
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from .config import ConfigError, Settings, load_settings
from .media.ffmpeg import CommandError
from .utils.files import ensure_data_dirs
from .utils.logger import add_file_log, log, setup_logging

app = typer.Typer(
    name="automeme",
    help="Auto Meme Video Editor — AI tìm khoảnh khắc phù hợp và chèn meme vào video.",
    no_args_is_help=True,
    add_completion=False,
)

VideoArg = Annotated[Path, typer.Argument(help="Video đầu vào (.mp4, .mov, .mkv).")]
ProfileOpt = Annotated[
    str | None,
    typer.Option("--profile", "-p", help="Profile trong configs/: subtle, funny, chaotic…"),
]
ForceOpt = Annotated[bool, typer.Option("--force", help="Làm lại dù đã có kết quả cũ.")]


def bootstrap(profile: str | None = None) -> Settings:
    """Nạp cấu hình theo profile, tạo thư mục data/ và bật file log. Sai cấu hình thì dừng."""
    try:
        settings = load_settings(profile)
    except ConfigError as e:
        log.error("%s", e)
        raise typer.Exit(code=1) from None
    ensure_data_dirs(settings.paths.data_dir)
    add_file_log(settings.paths.data_dir / "logs" / "automeme.log")
    return settings


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v",
                                               help="In log mức DEBUG.")] = False) -> None:
    """Bật log console và file data/logs/automeme.log trước mọi lệnh."""
    try:
        base = load_settings()
    except ConfigError:
        base = None  # `doctor` báo chi tiết; lệnh khác tự báo khi nạp cấu hình
    setup_logging("DEBUG" if verbose or base is None else base.app.log_level)
    if base is not None:
        add_file_log(base.paths.data_dir / "logs" / "automeme.log")


@app.command()
def doctor(profile: ProfileOpt = None) -> None:
    """Kiểm tra môi trường: Python, FFmpeg, GPU, Ollama, Docker, cấu hình."""
    from .doctor import FAIL, check_environment, format_checks

    settings, error = None, None
    try:
        settings = load_settings(profile)
    except ConfigError as e:
        error = str(e)
    rows = check_environment(settings, config_error=error, profile=profile)
    typer.echo(format_checks(rows))
    if any(status == FAIL for _, status, _ in rows):
        raise typer.Exit(code=1)


@app.command()
def transcribe(video: VideoArg, profile: ProfileOpt = None, force: ForceOpt = False) -> None:
    """Video → audio.wav → transcript.json (faster-whisper)."""
    from .pipeline import transcribe_video
    from .transcription.normalize import format_transcript_summary

    settings = bootstrap(profile)
    try:
        path, data = transcribe_video(video, settings, force=force)
    except (FileNotFoundError, CommandError, RuntimeError) as e:
        log.error("%s", e)
        raise typer.Exit(code=1) from None
    typer.echo(format_transcript_summary(data, path))


@app.command()
def analyze(video: VideoArg) -> None:
    """Transcript → các khoảnh khắc nên chèn meme (analysis.json)."""
    _chua_lam("analyze", "Iteration 3")


@app.command()
def inspect(
    timeline: Annotated[Path, typer.Argument(help="File timeline.json.")],
    video: Annotated[Path | None, typer.Option("--video", help="Video để kiểm tra cả thời "
                                                              "lượng và cỡ khung.")] = None,
    profile: ProfileOpt = None,
) -> None:
    """Xem lại timeline và kiểm tra trước khi render."""
    from .media.probe import probe
    from .timeline.schema import TimelineError, load_timeline
    from .timeline.validator import format_timeline_table, resolve_asset, validate_timeline

    settings = bootstrap(profile)
    try:
        tl = load_timeline(timeline)
    except TimelineError as e:
        log.error("%s", e)
        raise typer.Exit(code=1) from None

    thoi_luong = None
    if video is not None:
        try:
            thoi_luong = probe(video).duration
        except (CommandError, OSError) as e:
            log.warning("Không đọc được video (%s) — bỏ qua kiểm tra thời lượng.", e)

    goc = settings.paths.assets_dir.parent
    asset_paths = {e.asset: resolve_asset(e.asset, goc, settings.paths.assets_dir)
                   for e in tl.events}
    loi, canh_bao = validate_timeline(tl, video_duration=thoi_luong, asset_paths=asset_paths,
                                      meme_cfg=settings.meme, editing_cfg=settings.editing)
    typer.echo(format_timeline_table(tl, loi, canh_bao, thoi_luong))
    if loi:
        raise typer.Exit(code=1)


@app.command()
def render(
    video: VideoArg,
    timeline: Annotated[Path | None, typer.Option(
        "--timeline", help="Timeline dùng để dựng (mặc định: data/timelines/<tên>.timeline.json).",
    )] = None,
    out: Annotated[Path | None, typer.Option("--out", help="Nơi lưu video ra.")] = None,
    profile: ProfileOpt = None,
    force: ForceOpt = False,
) -> None:
    """Render meme vào video theo timeline.json (FFmpeg)."""
    from .pipeline import render_timeline
    from .timeline.schema import TimelineError

    settings = bootstrap(profile)
    try:
        path, tl = render_timeline(video, settings, timeline_path=timeline, output=out,
                                   force=force)
    except (FileNotFoundError, TimelineError, CommandError, ValueError) as e:
        log.error("%s", e)
        raise typer.Exit(code=1) from None
    typer.echo(f"Đã chèn {len(tl.events)} meme → {path}")


@app.command()
def run(video: VideoArg) -> None:
    """Chạy trọn pipeline: transcribe → analyze → tìm meme → timeline → render."""
    _chua_lam("run", "Iteration 4")


def _chua_lam(lenh: str, buoc: str) -> NoReturn:
    log.warning("Lệnh `automeme %s` chưa làm — thuộc %s trong lộ trình (docs/HANDOFF.md).",
                lenh, buoc)
    raise typer.Exit(code=1)
