"""Bước 3 — Tìm ứng viên bằng tín hiệu rẻ (không dùng AI).

Mọi tín hiệu được so với *mức nền cục bộ* (trung vị trượt), vì lượng người xem
và âm lượng mic thay đổi trong suốt buổi stream: 30 tin nhắn/10s là bình thường
lúc đông người nhưng là đột biến lúc vắng.
"""
from __future__ import annotations

import math
import re

import numpy as np

from .common import Job, log, read_json, write_json

# Mức tham chiếu cho điểm = 1.0 (có thể ghi đè trong settings.yaml → candidates.refs)
DEFAULT_REFS = {
    "loud_db": 12.0,     # to hơn mức nền 12 dB
    "chat_ratio": 4.0,   # chat gấp 4 lần mức nền
    "keywords": 1.0,     # số tin nhắn/lời nói có từ khóa ngang mức chat nền
}


def find_candidates(job: Job, settings: dict, streamer: dict) -> list[dict]:
    cfg = settings["candidates"]
    chat = read_json(job.chat) if job.chat.exists() else None
    loudness = read_json(job.loudness)
    words = read_json(job.words) if job.words.exists() else []

    signals = compute_signals(
        loudness=loudness, chat=chat, words=words,
        window=cfg["window_sec"],
        chat_tokens=cfg["chat_hype_tokens"],
        speech_keywords=streamer.get("tu_khoa_hype", []),
    )
    score = combine(signals, cfg["weights"], cfg["window_sec"], cfg["baseline_sec"], cfg.get("refs"))
    peaks = pick_peaks(score, cfg["window_sec"], cfg["top_k"], cfg["min_gap_sec"], cfg.get("min_score", 0.0))
    duration = len(loudness)
    cands = expand_and_merge(peaks, score, cfg["window_sec"], cfg["pre_sec"], cfg["post_sec"], duration)

    write_json(job.candidates, cands)
    log.info("Bước 3 xong: %d ứng viên", len(cands))
    return cands


# ------------------------------------------------------------------ tín hiệu
def compute_signals(*, loudness, chat, words, window, chat_tokens, speech_keywords) -> dict:
    duration = len(loudness)
    n = max(1, math.ceil(duration / window))
    # Cửa sổ cuối VOD thường thiếu dữ liệu (chat = 0, âm lượng lệch vì đệm) và hay tạo
    # đỉnh giả. Bỏ hẳn nếu nó ngắn hơn nửa cửa sổ.
    if n > 1 and duration - (n - 1) * window < window / 2:
        n -= 1

    loud = np.array(loudness, dtype=float)
    if len(loud) > n * window:
        loud = loud[: n * window]
    else:
        loud = np.pad(loud, (0, n * window - len(loud)), constant_values=loud.min() if len(loud) else -90)
    loud_win = loud.reshape(n, window).mean(axis=1)

    kw = np.zeros(n)
    tokens = [t.lower() for t in chat_tokens]
    chat_count = None
    if chat:
        chat_count = np.zeros(n)
        for m in chat:
            i = int(m["t"] // window)
            if 0 <= i < n:
                chat_count[i] += 1
                text = m["text"].lower()
                if any(tok in text for tok in tokens):
                    kw[i] += 1

    speech_kw = [_clean(k) for k in speech_keywords]
    single = {k for k in speech_kw if " " not in k}
    if speech_kw:
        for w in words:
            i = int(w["start"] // window)
            # so khớp nguyên từ: "ối" không được khớp nhầm vào "tối"
            if 0 <= i < n and _clean(w["w"]) in single:
                kw[i] += 1
        # từ khóa nhiều chữ ("sao lại thế") cần ghép các từ liền nhau
        _multiword_hits(words, speech_kw, window, kw)

    return {"chat": chat_count, "loudness": loud_win, "keywords": kw}


def _clean(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def _multiword_hits(words, keywords, window, kw) -> None:
    multi = [k for k in keywords if " " in k]
    if not multi:
        return
    for i in range(len(words)):
        phrase = " ".join(_clean(w["w"]) for w in words[i:i + 4])
        for k in multi:
            if phrase == k or phrase.startswith(k + " "):
                j = int(words[i]["start"] // window)
                if 0 <= j < len(kw):
                    kw[j] += 1


def rolling_median(x: np.ndarray, size: int) -> np.ndarray:
    size = max(1, size) | 1  # đảm bảo lẻ để cửa sổ cân giữa
    half = size // 2
    padded = np.pad(x, half, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, size)
    return np.median(windows, axis=1)


def _scale(x: np.ndarray, ref: float) -> np.ndarray:
    """Chia cho một mức tham chiếu có ý nghĩa vật lý (không dùng phân vị: với tín hiệu
    nhiễu, chuẩn hóa theo phân vị sẽ đẩy nhiễu lên ngang đỉnh thật). Chặn trên 1.5 để
    một tín hiệu cực lớn không lấn át hoàn toàn các tín hiệu khác."""
    return np.clip(x / ref, 0, 1.5)


def combine_parts(signals: dict, weights: dict, window: int, baseline_sec: int,
                  refs: dict | None = None) -> tuple[dict, dict]:
    """Điểm từng tín hiệu sau khi chuẩn hóa, và trọng số thực dùng (chia lại khi thiếu chat).

    Tách riêng khỏi `combine` để lệnh `inspect` in được đóng góp của từng tín hiệu.
    """
    refs = {**DEFAULT_REFS, **(refs or {})}
    base = max(3, baseline_sec // window)
    parts, used_w = {}, {}

    loud = signals["loudness"]
    parts["loudness"] = _scale(loud - rolling_median(loud, base), refs["loud_db"])  # dB trên mức nền
    used_w["loudness"] = weights["loudness"]

    chat = signals["chat"]
    if chat is not None and chat.sum() > 0:
        chat_base = rolling_median(chat, base)
        ratio = chat / (chat_base + 1)                     # gấp bao nhiêu lần mức nền
        parts["chat"] = _scale(ratio - 1, refs["chat_ratio"] - 1)
        used_w["chat"] = weights["chat"]
        kw_base = chat_base + 1
    else:
        kw_base = 1.0

    parts["keywords"] = _scale(signals["keywords"] / kw_base, refs["keywords"])
    used_w["keywords"] = weights["keywords"]
    return parts, used_w


def combine(signals: dict, weights: dict, window: int, baseline_sec: int, refs: dict | None = None) -> np.ndarray:
    parts, used_w = combine_parts(signals, weights, window, baseline_sec, refs)
    total = sum(used_w.values())  # chia lại trọng số khi thiếu chat
    return sum(parts[k] * (used_w[k] / total) for k in parts)


# ------------------------------------------------------------------ chọn đỉnh
def pick_peaks(score: np.ndarray, window: int, top_k: int, min_gap_sec: int, min_score: float = 0.0) -> list[int]:
    picked: list[int] = []
    min_gap = max(1, min_gap_sec // window)
    for i in np.argsort(-score):
        if score[i] <= min_score or len(picked) >= top_k:
            break
        if all(abs(int(i) - p) >= min_gap for p in picked):
            picked.append(int(i))
    return sorted(picked)


def expand_and_merge(peaks, score, window, pre, post, duration) -> list[dict]:
    max_len = 2 * (pre + post)
    spans = []
    for p in peaks:
        center = p * window + window / 2
        spans.append({"start": max(0.0, center - pre), "end": min(float(duration), center + post),
                      "peaks": [round(center, 1)], "score": float(score[p])})

    merged: list[dict] = []
    for s in spans:
        last = merged[-1] if merged else None
        if last and s["start"] <= last["end"] and s["end"] - last["start"] <= max_len:
            last["end"] = max(last["end"], s["end"])
            last["peaks"] += s["peaks"]
            last["score"] = max(last["score"], s["score"])
        else:
            merged.append(dict(s))

    for i, m in enumerate(merged, 1):
        m["id"] = f"k{i:02d}"
        m["start"], m["end"], m["score"] = round(m["start"], 1), round(m["end"], 1), round(m["score"], 3)
    return merged
