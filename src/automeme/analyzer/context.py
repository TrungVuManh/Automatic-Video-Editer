"""Dựng cửa sổ hội thoại quanh từng câu (SPEC §18)."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ContextWindow:
    segment_id: int
    start: float
    end: float
    previous: tuple[str, ...]
    current: str
    next: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["previous"] = list(self.previous)
        data["next"] = list(self.next)
        return data


def build_context_windows(transcript: dict[str, Any], *, previous_count: int = 2,
                          next_count: int = 1) -> list[ContextWindow]:
    """Mỗi đoạn thành một cửa sổ; không sửa transcript đầu vào."""
    if previous_count < 0 or next_count < 0:
        raise ValueError("Số đoạn ngữ cảnh không được âm.")
    segments = transcript.get("segments") or []
    windows: list[ContextWindow] = []
    for index, segment in enumerate(segments):
        windows.append(ContextWindow(
            segment_id=int(segment["id"]),
            start=float(segment["start"]),
            end=float(segment["end"]),
            previous=tuple(str(s["text"]) for s in segments[max(0, index - previous_count):index]),
            current=str(segment["text"]),
            next=tuple(str(s["text"]) for s in segments[index + 1:index + 1 + next_count]),
        ))
    return windows


LANG_DAI = 1.0  # im lặng từ chừng này giây luôn là ranh giới câu, dù mẩu trước ngắn


def split_long_segments(transcript: dict[str, Any], *, max_seconds: float, min_pause: float,
                        min_words: int = 3) -> dict[str, Any]:
    """Tách đoạn Whisper dài thành câu ngắn theo khoảng lặng giữa các từ. Không sửa đầu vào.

    Với lời nói liên tục (livestream), Whisper hay trả đoạn 6–17 s không dấu câu; meme neo ở
    cuối đoạn nên rơi trễ xa câu đùa. Dùng `words` (timestamp từng từ): cắt ở mọi khoảng lặng
    ≥ `min_pause` khi mẩu hiện tại đã đủ `min_words` từ (lặng ≥ `LANG_DAI` thì luôn cắt); mẩu
    vẫn dài hơn `max_seconds` thì chia đôi tại khoảng lặng lớn nhất (ưu tiên gần giữa). Đoạn
    không có timestamp từ thì giữ nguyên.
    """
    words = sorted(transcript.get("words") or [], key=lambda w: w["start"])
    out: list[dict[str, Any]] = []
    for seg in transcript.get("segments") or []:
        ws = [w for w in words if seg["start"] - 0.05 <= w["start"] < seg["end"]]
        if seg["end"] - seg["start"] <= max_seconds or len(ws) < 2 * min_words:
            out.append(dict(seg))
            continue
        for piece in _chia_theo_khoang_lang(ws, max_seconds, min_pause, min_words):
            out.append({"start": piece[0]["start"], "end": piece[-1]["end"],
                        "text": " ".join(str(w["w"]) for w in piece)})
    for i, seg in enumerate(out):
        seg["id"] = i
    return {**transcript, "segments": out}


def _chia_theo_khoang_lang(ws: list[dict[str, Any]], max_seconds: float, min_pause: float,
                           min_words: int) -> list[list[dict[str, Any]]]:
    pieces: list[list[dict[str, Any]]] = []
    cur = [ws[0]]
    for prev, w in zip(ws, ws[1:], strict=False):
        lang = w["start"] - prev["end"]
        if lang >= LANG_DAI or (lang >= min_pause and len(cur) >= min_words):
            pieces.append(cur)
            cur = [w]
        else:
            cur.append(w)
    pieces.append(cur)
    if (len(pieces) > 1 and len(pieces[-1]) < min_words
            and pieces[-1][0]["start"] - pieces[-2][-1]["end"] < LANG_DAI):
        duoi = pieces.pop()
        pieces[-1] += duoi  # mẩu cuối quá ngắn thì gộp vào mẩu trước
    result: list[list[dict[str, Any]]] = []
    for piece in pieces:
        result += _chia_doi(piece, max_seconds, min_words)
    return result


def _chia_doi(piece: list[dict[str, Any]], max_seconds: float,
              min_words: int) -> list[list[dict[str, Any]]]:
    if piece[-1]["end"] - piece[0]["start"] <= max_seconds or len(piece) < 2 * min_words:
        return [piece]
    giua = len(piece) / 2
    cat = max(range(min_words, len(piece) - min_words + 1),
              key=lambda k: (piece[k]["start"] - piece[k - 1]["end"], -abs(k - giua)))
    return (_chia_doi(piece[:cat], max_seconds, min_words)
            + _chia_doi(piece[cat:], max_seconds, min_words))
