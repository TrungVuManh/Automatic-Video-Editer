"""`automeme doctor` — kiểm tra môi trường (SPEC §9, Milestone 0).

Phần dò môi trường chỉ đọc, không sửa gì, và không ném lỗi — mục nào hỏng vẫn báo tiếp.
Phần phân tích kết quả (danh sách model Ollama, GPU) và dựng bảng là hàm thuần, có test.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date
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

    co_whisper = _importable("faster_whisper")
    rows.append(("faster-whisper", OK if co_whisper else WARN,
                 "đã cài" if co_whisper
                 else 'chưa cài — cần cho lệnh transcribe: python -m pip install -e ".[asr-cuda]" '
                      '(máy không có GPU: ".[asr]")'))
    rows.append(_gpu_row(settings))
    if co_whisper and (settings is None or settings.whisper.device != "cpu"):
        rows.append(ctranslate2_row())

    backend = settings.llm.backend if settings else "ollama"
    if backend == "claude":
        rows.append(_claude_row())
    elif settings:
        rows.append(ollama_status(settings.ollama.host, settings.ollama.model))

    rows.append(yt_dlp_row())
    rows.append(js_runtime_row(settings.download.js_runtime if settings else "auto"))

    for name, note in (("docker", "chỉ cần khi dùng Meme Search"),
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


def ctranslate2_row() -> Row:
    """CTranslate2 (lõi của faster-whisper) có thấy GPU không.

    Chỉ kiểm tra được tới mức "thấy GPU"; thiếu cuDNN thì phải nạp model mới lộ ra, khi đó
    `giai_thich_loi_model` sẽ nói rõ cách sửa.
    """
    try:
        import ctranslate2
    except ImportError:
        return ("CTranslate2 CUDA", WARN, "chưa cài ctranslate2")
    try:
        so = int(ctranslate2.get_cuda_device_count())
    except Exception as e:  # driver lỗi, build CPU-only…
        return ("CTranslate2 CUDA", WARN, f"không hỏi được GPU: {e}")
    if so > 0:
        return ("CTranslate2 CUDA", OK, f"thấy {so} GPU")
    return ("CTranslate2 CUDA", WARN,
            'không thấy GPU — cài python -m pip install -e ".[asr-cuda]", '
            "hoặc đặt WHISPER_DEVICE=cpu và WHISPER_COMPUTE_TYPE=int8")


YT_DLP_TUOI_TOI_DA = 90  # ngày — cùng ngưỡng cảnh báo "outdated" của chính yt-dlp


def yt_dlp_age_days(version: str, today: date) -> int | None:
    """Phiên bản yt-dlp đặt theo ngày phát hành ("2026.8.19") → số ngày tuổi, hoặc None."""
    try:
        year, month, day = (int(part) for part in version.split(".")[:3])
        return (today - date(year, month, day)).days
    except (ValueError, TypeError):
        return None


def yt_dlp_row(today: date | None = None) -> Row:
    """yt-dlp đã cài chưa và có quá cũ không — YouTube đổi liên tục, bản cũ hay hỏng."""
    try:
        from importlib.metadata import PackageNotFoundError, version
        ban = version("yt-dlp")
    except PackageNotFoundError:
        return ("yt-dlp", WARN, "chưa cài — cần cho lệnh download: python -m pip install -e .")
    tuoi = yt_dlp_age_days(ban, today or date.today())
    if tuoi is not None and tuoi > YT_DLP_TUOI_TOI_DA:
        return ("yt-dlp", WARN, f"{ban} đã {tuoi} ngày tuổi — YouTube hay đổi, nên cập nhật: "
                                "python -m pip install -U yt-dlp")
    return ("yt-dlp", OK, ban)


_TU_DO = object()  # giá trị mặc định: tự dò trên máy (test truyền giá trị cụ thể)


def ejs_pin_from_requirements(requirements: list[str] | None) -> str | None:
    """Bản `yt-dlp-ejs` mà yt-dlp ghim, đọc từ metadata: "yt-dlp-ejs==0.8.0; extra == …"."""
    for requirement in requirements or []:
        match = re.match(r"^yt-dlp-ejs\s*==\s*([\w.]+)", requirement.strip())
        if match:
            return match.group(1)
    return None


def _package_version(name: str) -> str | None:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _expected_ejs_version() -> str | None:
    from importlib.metadata import PackageNotFoundError, requires

    try:
        return ejs_pin_from_requirements(requires("yt-dlp"))
    except PackageNotFoundError:
        return None


def js_runtime_row(preference: str, solver_version: Any = _TU_DO,
                   expected_solver: Any = _TU_DO) -> Row:
    """JS runtime + script giải thử thách (gói `yt-dlp-ejs`) cho yt-dlp tải YouTube.

    Có runtime mà thiếu script thì yt-dlp vẫn tải được nhưng báo "n challenge solving failed":
    YouTube có thể bóp tốc độ hoặc ẩn bớt định dạng (đã gặp khi nghiệm thu 2026-09-17). Script
    phải đúng bản yt-dlp ghim — cập nhật yt-dlp mà không cập nhật script thì lại hỏng lặng lẽ.
    """
    from .media.youtube import pick_js_runtime

    if preference == "none":
        return ("JS runtime", WARN, "đã tắt (download.js_runtime=none) — YouTube có thể thiếu "
                                    "định dạng video")
    chon = pick_js_runtime(preference)
    if chon is None:
        can = "deno/node/bun" if preference == "auto" else preference
        return ("JS runtime", WARN, f"không thấy {can} — tải YouTube có thể thiếu định dạng; "
                                    "cài Deno: winget install DenoLand.Deno")
    if solver_version is _TU_DO:
        solver_version = _package_version("yt-dlp-ejs")
    if expected_solver is _TU_DO:
        expected_solver = _expected_ejs_version()
    lenh = f'python -m pip install "yt-dlp-ejs=={expected_solver}"' if expected_solver else (
        "python -m pip install -e .")
    if solver_version is None:
        return ("JS runtime", WARN, f"có {chon[0]} nhưng thiếu script giải thử thách (gói "
                                    f"yt-dlp-ejs) — YouTube có thể bóp tốc độ; cài: {lenh}")
    if expected_solver and solver_version != expected_solver:
        return ("JS runtime", WARN, f"yt-dlp-ejs {solver_version} không khớp bản yt-dlp cần "
                                    f"({expected_solver}) — chạy: {lenh}")
    return ("JS runtime", OK, f"{chon[0]} — {chon[1]} + yt-dlp-ejs {solver_version}")


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
    """Ollama chạy chưa, đã tải model chưa. Thiếu chỉ chặn lệnh `analyze` dùng local."""
    url = host.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            tags = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        hint = ("đã cài nhưng chưa chạy — mở ứng dụng Ollama" if which("ollama")
                else "chưa cài — winget install Ollama.Ollama")
        return ("Ollama", WARN, f"không kết nối được {host} ({hint}); cần cho `analyze`")
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
