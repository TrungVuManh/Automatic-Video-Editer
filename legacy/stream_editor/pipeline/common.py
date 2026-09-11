"""Tiện ích dùng chung: đường dẫn, đọc cấu hình, quản lý job, chạy lệnh ngoài."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
JOBS_DIR = ROOT / "jobs"
PROMPTS_DIR = ROOT / "prompts"
FEEDBACK_FILE = ROOT / "feedback" / "examples.jsonl"
MEME_LIBRARY = ROOT / "meme_library" / "library.jsonl"
FONTS_DIR = ROOT / "assets" / "fonts"   # font riêng cho phụ đề (tùy chọn)

log = logging.getLogger("auto_editor")


# ---------------------------------------------------------------- cấu hình
def load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_settings() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "settings.yaml")


def load_streamer(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"Không thấy preset {path}. Sao chép config/streamer_example.yaml để tạo mới."
        )
    return load_yaml(path)


# ---------------------------------------------------------------- job
@dataclass
class Job:
    """Mỗi VOD là một job, lưu trong jobs/<name>/."""

    name: str
    streamer: str
    platform: str  # youtube | twitch
    url: str | None = None
    local_video: str | None = None
    local_chat: str | None = None

    @property
    def dir(self) -> Path:
        return JOBS_DIR / self.name

    def path(self, *parts: str) -> Path:
        p = self.dir.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    # Các file chuẩn của pipeline
    @property
    def video(self) -> Path: return self.path("raw", "vod.mp4")
    @property
    def audio(self) -> Path: return self.path("raw", "audio.wav")
    @property
    def chat_raw(self) -> Path: return self.path("raw", "chat_raw.json")
    @property
    def chat(self) -> Path: return self.path("transcript", "chat.json")
    @property
    def words(self) -> Path: return self.path("transcript", "words.json")
    @property
    def segments(self) -> Path: return self.path("transcript", "segments.json")
    @property
    def loudness(self) -> Path: return self.path("transcript", "loudness.json")
    @property
    def candidates(self) -> Path: return self.path("candidates", "candidates.json")
    @property
    def clips(self) -> Path: return self.path("clips.json")

    def save(self) -> None:
        write_json(self.path("job.json"), asdict(self))

    @classmethod
    def load(cls, name: str) -> "Job":
        path = JOBS_DIR / name / "job.json"
        if not path.exists():
            raise FileNotFoundError(f"Job '{name}' chưa được tạo. Chạy `python run.py all ...` trước.")
        return cls(**read_json(path))


# ---------------------------------------------------------------- I/O
def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- lệnh ngoài
def require_binary(name: str) -> str:
    exe = shutil.which(name)
    if exe is None:
        raise RuntimeError(f"Không tìm thấy '{name}' trong PATH. Xem mục Cài đặt trong README.")
    return exe


def run_cmd(cmd: list[str], cwd: Path | None = None) -> str:
    r"""Chạy lệnh ngoài, trả về stdout.

    `cwd` dùng để đưa FFmpeg vào thư mục chứa file .ass: khi đó truyền được tên file
    tương đối, né hẳn việc phải escape `:` và `\` trong filter trên Windows.
    """
    log.debug("$ %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", cwd=str(cwd) if cwd else None)
    if result.returncode != 0:
        raise RuntimeError(f"Lệnh thất bại ({result.returncode}): {' '.join(cmd)}\n"
                           f"{(result.stderr or '')[-2000:]}")
    return result.stdout or ""


def probe_video_size(video: Path) -> tuple[int, int]:
    """Kích thước khung hình của luồng video đầu tiên, đọc bằng ffprobe."""
    exe = require_binary("ffprobe")
    out = run_cmd([exe, "-v", "error", "-select_streams", "v:0",
                   "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(video)])
    dong = [d for d in out.splitlines() if "x" in d]
    if not dong:
        raise RuntimeError(f"ffprobe không đọc được kích thước của {video}")
    w, h = dong[0].strip().split("x")[:2]
    return int(w), int(h)


def fmt_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}"


# ---------------------------------------------------------------- log
def setup_logging(verbose: bool = False) -> None:
    """Log ra console. Ép UTF-8 để không vỡ tiếng Việt trên console Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass  # stream bị chuyển hướng, không đổi được mã hóa

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(logging.DEBUG)  # lọc thật sự nằm ở từng handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S"))
    root.addHandler(console)


def add_file_log(job: "Job") -> Path:
    """Ghi thêm log (mức DEBUG) ra jobs/<job>/pipeline.log để gửi kèm khi báo lỗi."""
    path = job.path("pipeline.log")
    root = logging.getLogger()
    if any(getattr(h, "baseFilename", None) == str(path) for h in root.handlers):
        return path
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root.addHandler(handler)
    return path


# ---------------------------------------------------------------- chi phí API
# USD cho mỗi 1 triệu token (giá API Anthropic hạng nhất, tra 2026-06).
# Khớp theo tiền tố nên id có hậu tố ngày ("claude-haiku-4-5-20251001") vẫn nhận ra.
PRICING = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}
CACHE_READ_RATE = 0.1    # đọc từ cache rẻ hơn ~10 lần
CACHE_WRITE_RATE = 1.25  # ghi vào cache đắt hơn 25%


def _price_of(model: str) -> tuple[float, float] | None:
    for key in sorted(PRICING, key=len, reverse=True):
        if model.startswith(key):
            return PRICING[key]
    return None


def estimate_cost(model: str, input_tokens: int, output_tokens: int,
                  cache_read: int = 0, cache_write: int = 0) -> float:
    """Ước tính chi phí (USD) của một lần gọi API. Model lạ → 0.0."""
    price = _price_of(model)
    if price is None:
        return 0.0
    p_in, p_out = price
    usd = (input_tokens * p_in
           + output_tokens * p_out
           + cache_read * p_in * CACHE_READ_RATE
           + cache_write * p_in * CACHE_WRITE_RATE) / 1_000_000
    return round(usd, 6)


USAGE_KEYS = ("input_tokens", "output_tokens", "cache_write", "cache_read")


def usage_entry(step: str, model: str, usage: Any) -> dict:
    """Đổi object usage của SDK thành dict thuần (SDK cũ có thể thiếu trường cache)."""
    def field(name: str) -> int:
        return int(getattr(usage, name, 0) or 0)

    entry = {
        "luc": datetime.now().isoformat(timespec="seconds"),
        "step": step,
        "model": model,
        "input_tokens": field("input_tokens"),
        "output_tokens": field("output_tokens"),
        "cache_write": field("cache_creation_input_tokens"),
        "cache_read": field("cache_read_input_tokens"),
    }
    entry["cost_usd"] = estimate_cost(model, entry["input_tokens"], entry["output_tokens"],
                                      entry["cache_read"], entry["cache_write"])
    return entry


def sum_usage(entries: list[dict]) -> dict:
    total = {k: sum(e.get(k, 0) for e in entries) for k in USAGE_KEYS}
    total["so_lan_goi"] = len(entries)
    total["cost_usd"] = round(sum(e.get("cost_usd", 0.0) for e in entries), 6)
    return total


def record_usage(job: "Job", step: str, model: str, usage: Any) -> dict:
    """Cộng dồn token của một lần gọi API vào jobs/<job>/usage.json."""
    entry = usage_entry(step, model, usage)
    path = job.path("usage.json")
    data = read_json(path) if path.exists() else {"lan_goi": []}
    data["lan_goi"].append(entry)
    data["tong"] = sum_usage(data["lan_goi"])
    write_json(path, data)
    log.info("Token (%s): vào %d, ra %d — ước tính $%.4f",
             step, entry["input_tokens"], entry["output_tokens"], entry["cost_usd"])
    return entry
