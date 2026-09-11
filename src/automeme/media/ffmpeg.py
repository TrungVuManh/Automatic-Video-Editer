r"""Chạy lệnh ngoài (FFmpeg, ffprobe…).

Lệnh luôn truyền dạng list, không ghép chuỗi (SPEC §40) — tránh lỗi escape đường dẫn
trên Windows. Filter nào cần tên file (ví dụ `ass=`) thì chạy với `cwd` là thư mục chứa
file và truyền tên tương đối, để chuỗi filter không bao giờ chứa `:` hay `\`.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from ..utils.logger import log


class CommandError(RuntimeError):
    """Lệnh ngoài chạy thất bại hoặc trả về dữ liệu không đọc được."""


def which(name: str) -> str | None:
    """Như shutil.which nhưng tìm thêm trong Scripts/ (bin/) của môi trường ảo đang chạy."""
    return shutil.which(name) or shutil.which(name, path=str(Path(sys.executable).parent))


def require_binary(name: str) -> str:
    exe = which(name)
    if exe is None:
        raise CommandError(
            f"Không tìm thấy '{name}' trong PATH. Với FFmpeg: `winget install Gyan.FFmpeg` "
            f"rồi mở lại terminal. Chạy `automeme doctor` để kiểm tra môi trường."
        )
    return exe


def run_cmd(cmd: list[str], cwd: Path | None = None) -> str:
    """Chạy lệnh, trả về stdout. Lỗi thì ném CommandError kèm phần cuối stderr."""
    printable = subprocess.list2cmdline(cmd)
    log.debug("$ %s", printable)
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(cwd) if cwd else None,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()[-2000:]
        raise CommandError(f"Lệnh thất bại (mã {result.returncode}): {printable}\n{stderr}")
    return result.stdout or ""


def parse_ffmpeg_version(text: str) -> str | None:
    """'ffmpeg version 9.0.1-full_build-www.gyan.dev Copyright…' → '9.0.1-full_build-…'."""
    m = re.search(r"\bversion\s+(\S+)", text or "")
    return m.group(1) if m else None


def ffmpeg_version(exe: str = "ffmpeg") -> str | None:
    """Phiên bản của ffmpeg/ffprobe; None nếu không chạy được."""
    try:
        return parse_ffmpeg_version(run_cmd([exe, "-version"]))
    except (CommandError, OSError):
        return None
