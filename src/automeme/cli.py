"""CLI `automeme` (Typer) — SPEC §44–45.

Lệnh chưa làm sẽ báo rõ thuộc iteration nào trong docs/HANDOFF.md và thoát với mã 1.
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from .config import ConfigError, load_settings
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
def transcribe(video: VideoArg) -> None:
    """Video → audio.wav → transcript.json (faster-whisper)."""
    _chua_lam("transcribe", "Iteration 1")


@app.command()
def analyze(video: VideoArg) -> None:
    """Transcript → các khoảnh khắc nên chèn meme (analysis.json)."""
    _chua_lam("analyze", "Iteration 3")


@app.command()
def inspect(timeline: Annotated[Path, typer.Argument(help="File timeline.json.")]) -> None:
    """Xem lại timeline trước khi render."""
    _chua_lam("inspect", "Iteration 2")


@app.command()
def render(video: VideoArg) -> None:
    """Render meme vào video theo timeline.json (FFmpeg)."""
    _chua_lam("render", "Iteration 2")


@app.command()
def run(video: VideoArg) -> None:
    """Chạy trọn pipeline: transcribe → analyze → tìm meme → timeline → render."""
    _chua_lam("run", "Iteration 4")


def _chua_lam(lenh: str, buoc: str) -> NoReturn:
    log.warning("Lệnh `automeme %s` chưa làm — thuộc %s trong lộ trình (docs/HANDOFF.md).",
                lenh, buoc)
    raise typer.Exit(code=1)
