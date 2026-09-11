"""Hai lệnh phụ trợ khi chạy thật: `doctor` (kiểm tra môi trường) và `inspect`
(in bảng điểm từng tín hiệu tại mỗi đỉnh, để tinh chỉnh `candidates.refs`/`weights`).

Phần dựng bảng là hàm thuần, có test; phần dò môi trường chỉ đọc, không sửa gì.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from .common import Job, read_json
from .s3_candidates import combine_parts, compute_signals, rolling_median

# (tên, bắt buộc?, ghi chú) — công cụ ngoài mà pipeline cần
BINARIES = [
    ("ffmpeg", True, "bắt buộc: cắt/ghép/render video"),
    ("ffprobe", True, "bắt buộc: đọc kích thước khung hình cho layout dọc"),
    ("ffplay", False, "tùy chọn: xem thử clip khi duyệt trên terminal"),
    ("yt-dlp", False, "cần khi tải VOD/chat từ link (không cần nếu dùng --video)"),
    ("TwitchDownloaderCLI", False, "chỉ cần khi tải chat Twitch"),
]

# Ba trạng thái: đạt / thiếu nhưng chưa chặn / hỏng phải sửa
OK, WARN, FAIL = "ok", "warn", "fail"
NHAN = {OK: "  OK  ", WARN: "THIẾU ", FAIL: " HỎNG "}


# ---------------------------------------------------------------- doctor
def which(name: str) -> str | None:
    """Như shutil.which nhưng tìm thêm trong Scripts/bin của môi trường ảo đang chạy."""
    return shutil.which(name) or shutil.which(name, path=str(Path(sys.executable).parent))


def check_environment() -> list[tuple[str, str, str]]:
    """Trả về [(hạng mục, trạng thái, chi tiết)]. Không ném lỗi — mục nào hỏng vẫn báo tiếp."""
    rows: list[tuple[str, str, str]] = []

    v = sys.version_info
    rows.append(("Python >= 3.10", OK if v >= (3, 10) else FAIL,
                 f"đang dùng {v.major}.{v.minor}.{v.micro}"))

    for name, required, note in BINARIES:
        path = which(name)
        if path:
            rows.append((name, OK, path))
        else:
            rows.append((name, FAIL if required else WARN, f"không thấy trong PATH — {note}"))

    key = os.environ.get("ANTHROPIC_API_KEY", "")
    rows.append(("ANTHROPIC_API_KEY", OK if key else FAIL,
                 f"đã đặt (…{key[-4:]})" if key else "chưa đặt — tạo file .env từ .env.example"))

    for mod, note in [("numpy", "bắt buộc"), ("soundfile", "bắt buộc: đo âm lượng"),
                      ("yaml", "bắt buộc"), ("anthropic", "bắt buộc: gọi Claude")]:
        ok = _importable(mod)
        rows.append((f"python: {mod}", OK if ok else FAIL,
                     note if ok else f"{note} — pip install -r requirements.txt"))

    backend = next((m for m in ("whisperx", "faster_whisper") if _importable(m)), None)
    rows.append(("ASR backend", OK if backend else WARN,
                 backend or "chưa cài — chỉ cần cho bước preprocess; "
                            "pip install -r requirements-asr.txt (cài PyTorch CUDA trước)"))

    torch_ok, torch_note = _cuda_status()
    rows.append(("GPU (CUDA)", OK if torch_ok else WARN, torch_note))

    utf8 = bool(sys.stdout.encoding and "utf-8" in sys.stdout.encoding.lower())
    rows.append(("Console UTF-8", OK if utf8 else WARN,
                 f"encoding={sys.stdout.encoding}" + ("" if utf8 else " — đặt PYTHONUTF8=1")))
    return rows


def _importable(module: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _cuda_status() -> tuple[bool, str]:
    try:
        import torch
    except ImportError:
        return False, "chưa cài torch — ASR sẽ chạy CPU (rất chậm) hoặc không chạy được"
    if torch.cuda.is_available():
        return True, f"{torch.cuda.get_device_name(0)} (torch {torch.__version__})"
    return False, f"torch {torch.__version__} không thấy CUDA — đặt asr.device=cpu, compute_type=int8"


def format_checks(rows: list[tuple[str, str, str]]) -> str:
    """Dựng bảng kết quả kiểm tra môi trường."""
    width = max((len(name) for name, _, _ in rows), default=10)
    lines = ["", "KIỂM TRA MÔI TRƯỜNG", "-" * (width + 46)]
    for name, status, detail in rows:
        lines.append(f"  [{NHAN[status]}]  {name.ljust(width)}  {detail}")
    lines.append("-" * (width + 46))

    hong = [name for name, st, _ in rows if st == FAIL]
    thieu = [name for name, st, _ in rows if st == WARN]
    lines.append("Bắt buộc: " + ("tất cả đạt." if not hong else "CẦN SỬA — " + ", ".join(hong)))
    if thieu:
        lines.append("Thiếu nhưng chưa chặn: " + ", ".join(thieu))
    return "\n".join(lines)


# ---------------------------------------------------------------- inspect
def build_inspect_rows(job: Job, settings: dict, streamer: dict) -> list[dict]:
    """Với mỗi đỉnh của mỗi ứng viên: giá trị thô và điểm đã chuẩn hóa của từng tín hiệu."""
    cfg = settings["candidates"]
    window = cfg["window_sec"]
    loudness = read_json(job.loudness)
    chat = read_json(job.chat) if job.chat.exists() else None
    words = read_json(job.words) if job.words.exists() else []
    cands = read_json(job.candidates)

    signals = compute_signals(loudness=loudness, chat=chat, words=words, window=window,
                              chat_tokens=cfg["chat_hype_tokens"],
                              speech_keywords=streamer.get("tu_khoa_hype", []))
    parts, used_w = combine_parts(signals, cfg["weights"], window, cfg["baseline_sec"], cfg.get("refs"))
    total_w = sum(used_w.values())

    base = max(3, cfg["baseline_sec"] // window)
    loud_base = rolling_median(signals["loudness"], base)
    chat_base = rolling_median(signals["chat"], base) if signals["chat"] is not None else None
    n = len(signals["loudness"])

    rows = []
    for c in cands:
        for peak in c["peaks"]:
            i = int(peak // window)
            if not 0 <= i < n:
                continue
            row = {
                "id": c["id"], "t": float(peak),
                "chat": float(signals["chat"][i]) if signals["chat"] is not None else 0.0,
                "chat_nen": float(chat_base[i]) if chat_base is not None else 0.0,
                "loud": float(signals["loudness"][i]),
                "loud_nen": float(loud_base[i]),
                "kw": float(signals["keywords"][i]),
                "tong": 0.0,
            }
            for key in ("chat", "loudness", "keywords"):
                p = float(parts[key][i]) if key in parts else 0.0
                row[f"p_{key}"] = p
                row["tong"] += p * (used_w.get(key, 0.0) / total_w if key in parts else 0.0)
            rows.append(row)
    return rows


def format_inspect_table(rows: list[dict]) -> str:
    """Bảng: giá trị thô | điểm đã chuẩn hóa (0–1.5) | tổng có trọng số."""
    if not rows:
        return "Không có đỉnh nào để xem. Chạy bước candidates trước."
    head = (f"{'mã':<5} {'thời điểm':>9} | {'chat':>6} {'nền':>6} {'dB':>7} {'trên nền':>8} "
            f"{'từ khóa':>7} | {'p.chat':>6} {'p.dB':>6} {'p.từ':>6} | {'TỔNG':>6}")
    lines = ["", "ĐIỂM TÍN HIỆU TẠI TỪNG ĐỈNH", head, "-" * len(head)]
    for r in rows:
        lines.append(
            f"{r['id']:<5} {_hms(r['t']):>9} | {r['chat']:>6.0f} {r['chat_nen']:>6.1f} "
            f"{r['loud']:>7.1f} {r['loud'] - r['loud_nen']:>+8.1f} {r['kw']:>7.0f} | "
            f"{r['p_chat']:>6.2f} {r['p_loudness']:>6.2f} {r['p_keywords']:>6.2f} | {r['tong']:>6.3f}"
        )
    lines += ["-" * len(head),
              "p.* là điểm sau chuẩn hóa theo candidates.refs (1.0 = đạt mức tham chiếu).",
              "p.chat luôn kịch trần 1.5 → tăng refs.chat_ratio; luôn ~0 → giảm."]
    return "\n".join(lines)


def _hms(sec: float) -> str:
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}"
