"""Log: console (mức theo cấu hình, DEBUG khi có -v) và file data/logs/automeme.log (DEBUG).

Mọi module ghi log qua `log` ở đây, không dùng print() (SPEC §47). Log bằng tiếng Việt.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

log = logging.getLogger("automeme")

CONSOLE_FORMAT = "[%(asctime)s] %(levelname)-7s %(message)s"
FILE_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_TAG = "_automeme_handler"  # đánh dấu handler do ta thêm, để gỡ đúng cái của mình


class _StdoutHandler(logging.StreamHandler):
    """Luôn ghi vào `sys.stdout` hiện tại thay vì stream lúc khởi tạo — không hỏng khi
    stdout bị thay (CliRunner lúc test)."""

    def __init__(self) -> None:
        super().__init__(sys.stdout)

    @property
    def stream(self):  # type: ignore[override]
        return sys.stdout

    @stream.setter
    def stream(self, value) -> None:
        pass


def force_utf8_console() -> None:
    """Ép stdout/stderr về UTF-8 để không vỡ tiếng Việt trên console Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass  # stream đã bị chuyển hướng, không đổi được mã hóa


def setup_logging(level: str = "INFO") -> None:
    """Gọi lại nhiều lần được: gỡ handler cũ của mình trước khi thêm mới.

    Logger `automeme` ở mức DEBUG, logger gốc ở WARNING: log của thư viện ngoài chỉ hiện khi
    là cảnh báo/lỗi, còn log của mình được lọc ở từng handler.
    """
    force_utf8_console()
    root = logging.getLogger()
    for h in [h for h in root.handlers if getattr(h, _TAG, False)]:
        root.removeHandler(h)
        h.close()
    root.setLevel(logging.WARNING)
    log.setLevel(logging.DEBUG)

    console = _StdoutHandler()
    console.setLevel(level.upper())
    console.setFormatter(logging.Formatter(CONSOLE_FORMAT, "%H:%M:%S"))
    setattr(console, _TAG, True)
    root.addHandler(console)


def add_file_log(path: Path) -> Path:
    """Ghi thêm log mức DEBUG (kèm nguyên lệnh FFmpeg) ra file — gửi kèm khi báo lỗi.

    Xoay vòng ở 5 MB, giữ 3 file cũ.
    """
    root = logging.getLogger()
    target = os.path.abspath(path)
    if any(getattr(h, "baseFilename", None) == target for h in root.handlers):
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(FILE_FORMAT))
    setattr(handler, _TAG, True)
    root.addHandler(handler)
    return path
