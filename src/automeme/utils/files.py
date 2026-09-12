"""Đường dẫn chuẩn của dự án và đọc/ghi file (luôn UTF-8)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# src/automeme/utils/files.py → lùi 3 cấp là thư mục gốc dự án (cài bằng `pip install -e .`)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIGS_DIR = PROJECT_ROOT / "configs"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
ENV_FILE = PROJECT_ROOT / ".env"

# Các thư mục con của data/ (SPEC §12) + logs/
DATA_SUBDIRS = (
    "input", "temp", "cache", "transcripts", "analysis", "timelines", "output", "logs",
)


def resolve_path(path: str | Path, root: Path = PROJECT_ROOT) -> Path:
    """Đường dẫn tương đối được tính từ `root` (mặc định: thư mục gốc dự án)."""
    p = Path(path).expanduser()
    return p if p.is_absolute() else (root / p).resolve()


def ensure_data_dirs(data_dir: Path) -> None:
    for name in DATA_SUBDIRS:
        (data_dir / name).mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    """Ghi JSON giữ nguyên dấu tiếng Việt.

    Ghi ra file tạm rồi mới đổi tên: bị ngắt giữa chừng cũng không để lại file dở dang —
    quan trọng vì mỗi bước bỏ qua nếu output đã tồn tại.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
