"""Chuẩn hóa transcript thô thành schema của dự án, và kiểm tra kết quả.

Toàn bộ là hàm thuần, không đụng tới file. Schema (SPEC §17, thêm `words` và `model`):

    {
      "video": "wedding.mp4",
      "language": "vi",
      "duration": 47.83,
      "model": "large-v3",
      "segments": [{"id": 0, "start": 0.42, "end": 3.21, "text": "Hôm nay..."}],
      "words": [{"w": "Hôm", "start": 0.42, "end": 0.6}]
    }
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..utils.timestamps import format_ts

LAP_TOI_DA = 3  # số lần một câu lặp liên tiếp trước khi coi là Whisper bị "kẹt"


def clean_text(text: Any) -> str:
    """Gộp mọi khoảng trắng thành một dấu cách và cắt hai đầu."""
    return " ".join(str(text or "").split())


def normalize_transcript(raw: dict[str, Any], *, video_name: str, model: str,
                         duration: float | None = None) -> dict[str, Any]:
    """Dict thô của backend → schema của dự án.

    Bỏ đoạn rỗng hoặc có thời gian vô lý, sắp xếp theo thời gian, đánh lại `id` từ 0.
    `duration` (đo bằng ffprobe) được ưu tiên hơn con số backend tự báo.
    """
    segments: list[dict[str, Any]] = []
    words: list[dict[str, Any]] = []

    for seg in raw.get("segments") or []:
        text = clean_text(seg.get("text"))
        start, end = _so(seg.get("start")), _so(seg.get("end"))
        if not text or start is None or end is None or end <= start:
            continue
        segments.append({"id": 0, "start": round(start, 2), "end": round(end, 2), "text": text})
        for w in seg.get("words") or []:
            tu = clean_text(w.get("w"))
            ws, we = _so(w.get("start")), _so(w.get("end"))
            # Từ không căn được thời gian sẽ thiếu start/end — bỏ, đừng đoán
            if tu and ws is not None and we is not None and we > ws:
                words.append({"w": tu, "start": round(ws, 2), "end": round(we, 2)})

    segments.sort(key=lambda s: (s["start"], s["end"]))
    for i, seg in enumerate(segments):
        seg["id"] = i
    words.sort(key=lambda w: (w["start"], w["end"]))

    tong = duration if duration is not None else _so(raw.get("duration"))
    if tong is None and segments:
        tong = segments[-1]["end"]

    return {
        "video": video_name,
        "language": clean_text(raw.get("language")) or "",
        "duration": round(float(tong), 2) if tong is not None else None,
        "model": model,
        "segments": segments,
        "words": words,
    }


def validate_transcript(data: dict[str, Any]) -> list[str]:
    """Những dấu hiệu bất thường đáng cảnh báo (không ném lỗi — transcript vẫn dùng được)."""
    canh_bao: list[str] = []
    segments = data.get("segments") or []
    words = data.get("words") or []
    duration = data.get("duration")

    if not segments:
        canh_bao.append("không nhận được câu nào — video có tiếng nói không? "
                        "Thử WHISPER_VAD_FILTER=false hoặc kiểm tra file audio.")
        return canh_bao

    if not words:
        canh_bao.append("không có timestamp theo từ — việc canh meme đúng cuối câu sẽ kém "
                        "chính xác. Kiểm tra backend có bật word_timestamps không.")

    truoc = None
    for seg in segments:
        if seg["end"] <= seg["start"]:
            canh_bao.append(f"đoạn {seg['id']} có thời gian không hợp lệ "
                            f"({seg['start']} → {seg['end']})")
        if truoc is not None and seg["start"] < truoc:
            canh_bao.append(f"đoạn {seg['id']} bắt đầu trước khi đoạn trước kết thúc")
        truoc = seg["end"]
        if duration and seg["end"] > duration + 1.0:
            canh_bao.append(f"đoạn {seg['id']} kết thúc ở {format_ts(seg['end'])}, "
                            f"vượt quá thời lượng video ({format_ts(duration)})")

    lap = _lap_lien_tiep(segments)
    if lap:
        canh_bao.append(f"câu \"{lap}\" lặp liên tiếp nhiều lần — Whisper có thể đang bịa; "
                        f"thử bật lại VAD hoặc đổi model")
    return canh_bao


def format_transcript_summary(data: dict[str, Any], path: Path, so_dong: int = 5) -> str:
    """Vài dòng tóm tắt in ra sau khi chạy xong."""
    segments = data.get("segments") or []
    dong = [f"Transcript: {len(segments)} đoạn, {len(data.get('words') or [])} từ, "
            f"{data.get('duration') or 0:.1f} giây ({data.get('model')})"]
    for seg in segments[:so_dong]:
        dong.append(f"  [{format_ts(seg['start'])}] {seg['text']}")
    if len(segments) > so_dong:
        dong.append(f"  … còn {len(segments) - so_dong} đoạn nữa")
    dong.append(f"→ {path}")
    return "\n".join(dong)


def _so(value: Any) -> float | None:
    try:
        so = float(value)
    except (TypeError, ValueError):
        return None
    return so if so >= 0 else None


def _lap_lien_tiep(segments: list[dict[str, Any]]) -> str | None:
    dem, truoc = 1, None
    for seg in segments:
        if truoc is not None and seg["text"] == truoc:
            dem += 1
            if dem >= LAP_TOI_DA:
                return truoc
        else:
            dem = 1
        truoc = seg["text"]
    return None
