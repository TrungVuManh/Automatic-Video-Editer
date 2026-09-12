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
