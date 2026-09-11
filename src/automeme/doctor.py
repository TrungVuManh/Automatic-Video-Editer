"""`automeme doctor` — kiểm tra môi trường (SPEC §9, Milestone 0).

Phần dò môi trường chỉ đọc, không sửa gì, và không ném lỗi — mục nào hỏng vẫn báo tiếp.
Phần phân tích kết quả (danh sách model Ollama, GPU) và dựng bảng là hàm thuần, có test.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
import urllib.request
from typing import Any

from .config import Settings, read_env
from .media.ffmpeg import CommandError, ffmpeg_version, run_cmd, which
from .utils.files import ENV_FILE

# Ba trạng thái: đạt / thiếu nhưng chưa chặn việc đang làm được / hỏng phải sửa
OK, WARN, FAIL = "ok", "warn", "fail"
NHAN = {OK: "  OK  ", WARN: "THIẾU ", FAIL: " HỎNG "}

Row = tuple[str, str, str]  # (hạng mục, trạng thái, chi tiết)


def check_environment(settings: Settings | None, config_error: str | None = None,
                      profile: str | None = None) -> list[Row]:
    rows: list[Row] = []

    v = sys.version_info
    rows.append(("Python >= 3.10", OK if v >= (3, 10) else FAIL,
                 f"{v.major}.{v.minor}.{v.micro} — {sys.executable}"))

    if config_error:
        rows.append(("Cấu hình", FAIL, config_error.replace("\n", " ")))
    else:
        rows.append(("Cấu hình", OK, f"profile: {profile or 'default'}"))
    rows.append((".env", OK if ENV_FILE.exists() else WARN,
                 "đã có" if ENV_FILE.exists()
                 else "chưa có — đang dùng giá trị mặc định; tạo: Copy-Item .env.example .env"))

    for name in ("ffmpeg", "ffprobe"):
        exe = which(name)
        if exe:
            rows.append((name, OK, f"{ffmpeg_version(exe) or '?'} — {exe}"))
        else:
            rows.append((name, FAIL, "không thấy trong PATH — winget install Gyan.FFmpeg"))

    rows.append(("faster-whisper", OK if _importable("faster_whisper") else WARN,
                 "đã cài" if _importable("faster_whisper")
                 else "chưa cài — cần từ Iteration 1: python -m pip install -e .[asr]"))
    rows.append(_gpu_row(settings))

    backend = settings.llm.backend if settings else "ollama"
    if backend == "claude":
        rows.append(_claude_row())
    elif settings:
        rows.append(ollama_status(settings.ollama.host, settings.ollama.model))

    for name, note in (("docker", "chỉ cần cho Meme Search (Iteration 4)"),
                       ("git", "quản lý phiên bản")):
        exe = which(name)
        rows.append((name, OK if exe else WARN, exe or f"không thấy — {note}"))

    enc = sys.stdout.encoding or ""
    utf8 = enc.lower().replace("-", "") == "utf8"
    rows.append(("Console UTF-8", OK if utf8 else WARN,
                 f"encoding={enc}" + ("" if utf8 else " — đặt biến môi trường PYTHONUTF8=1")))
    return rows


# ------------------------------------------------------------------ từng hạng mục
def _importable(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _gpu_row(settings: Settings | None) -> Row:
    gpus = gpu_names()
    if gpus:
        return ("GPU NVIDIA", OK, "; ".join(gpus))
    if settings and settings.whisper.device == "cpu":
        return ("GPU NVIDIA", OK, "không có — whisper.device=cpu nên không cần")
    return ("GPU NVIDIA", WARN, "không thấy (nvidia-smi) — Whisper trên CPU rất chậm; "
                                "nếu vẫn chạy CPU: WHISPER_DEVICE=cpu, WHISPER_COMPUTE_TYPE=int8")


def gpu_names() -> list[str]:
    exe = which("nvidia-smi")
    if not exe:
        return []
    try:
        return parse_nvidia_smi(run_cmd([exe, "--query-gpu=name,memory.total",
                                         "--format=csv,noheader"]))
    except (CommandError, OSError):
        return []


def parse_nvidia_smi(text: str) -> list[str]:
    """'NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB' (mỗi GPU một dòng) → ['… (8188 MiB)']."""
    out = []
    for line in (text or "").splitlines():
        name, _, mem = line.partition(",")
        if name.strip():
            out.append(f"{name.strip()} ({mem.strip()})" if mem.strip() else name.strip())
    return out


def ollama_status(host: str, model: str, timeout: float = 2.0) -> Row:
    """Ollama chạy chưa, đã tải model chưa. Cần từ Iteration 3 nên thiếu chỉ là cảnh báo."""
    url = host.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            tags = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        hint = ("đã cài nhưng chưa chạy — mở ứng dụng Ollama" if which("ollama")
                else "chưa cài — winget install Ollama.Ollama")
        return ("Ollama", WARN, f"không kết nối được {host} ({hint}); cần từ Iteration 3")
    if has_model(ollama_model_names(tags), model):
        return ("Ollama", OK, f"{host} — có model {model}")
    return ("Ollama", WARN, f"server chạy nhưng chưa có {model} — chạy: ollama pull {model}")


def ollama_model_names(tags: dict[str, Any]) -> list[str]:
    """JSON của GET /api/tags → danh sách tên model."""
    return [str(m.get("name") or m.get("model")) for m in tags.get("models") or []
            if m.get("name") or m.get("model")]


def has_model(names: list[str], model: str) -> bool:
    """So tên model, coi `qwen3` và `qwen3:latest` là một."""
    def chuan(n: str) -> str:
        return n if ":" in n else f"{n}:latest"
    return chuan(model) in {chuan(n) for n in names}


def _claude_row() -> Row:
    if not _importable("anthropic"):
        return ("Claude API", FAIL, "llm.backend=claude nhưng chưa cài: "
                                    "python -m pip install -e .[claude]")
    key = read_env().get("ANTHROPIC_API_KEY", "")
    if not key:
        return ("Claude API", FAIL,
                "llm.backend=claude nhưng chưa đặt ANTHROPIC_API_KEY trong .env")
    return ("Claude API", OK, f"đã đặt key (…{key[-4:]})")


# ------------------------------------------------------------------ bảng
def format_checks(rows: list[Row]) -> str:
    width = max((len(name) for name, _, _ in rows), default=10)
    rule = "-" * (width + 50)
    lines = ["", "KIỂM TRA MÔI TRƯỜNG", rule]
    lines += [f"  [{NHAN[status]}]  {name.ljust(width)}  {detail}" for name, status, detail in rows]
    lines.append(rule)

    hong = [name for name, status, _ in rows if status == FAIL]
    thieu = [name for name, status, _ in rows if status == WARN]
    lines.append("Bắt buộc: " + ("tất cả đạt." if not hong else "CẦN SỬA — " + ", ".join(hong)))
    if thieu:
        lines.append("Thiếu nhưng chưa chặn: " + ", ".join(thieu))
    return "\n".join(lines)
