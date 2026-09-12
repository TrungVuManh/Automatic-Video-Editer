"""Định dạng `timeline.json` (SPEC §34) và việc đọc/ghi nó.

Timeline là bản dựng dạng chữ: người sửa được bằng tay rồi render lại mà không tốn lượt AI.
Vì vậy schema chặt (khóa lạ bị báo lỗi) và thông báo lỗi phải nói rõ sai ở đâu.

Timeline hỗ trợ cả overlay `meme` và âm thanh ngắn `sfx`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..utils.files import read_json, write_json

VI_TRI = ("top-left", "top-right", "bottom-left", "bottom-right", "center")
ViTri = Literal["top-left", "top-right", "bottom-left", "bottom-right", "center"]

SCALE_MIN, SCALE_MAX = 0.05, 1.0


class TimelineError(ValueError):
    """Timeline sai định dạng hoặc không đọc được."""


class MemeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["meme"] = "meme"
    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    asset: str
    mode: Literal["overlay"] = "overlay"  # cutaway làm ở giai đoạn sau (SPEC §36)
    # Để trống thì lấy mặc định trong configs/ (meme.position_default, meme.scale_default)
    position: ViTri | None = None
    scale: float | None = Field(default=None, ge=SCALE_MIN, le=SCALE_MAX)
    # Thông tin do bước phân tích sinh ra, giữ lại để người duyệt hiểu vì sao có meme này
    confidence: float | None = Field(default=None, ge=0, le=1)
    query: str | None = None
    reason: str | None = None
    # Giao diện review giữ sự kiện bị từ chối để có thể hoàn tác; renderer chỉ lấy active_events.
    status: Literal["pending", "accepted", "rejected"] = "pending"

    @property
    def end(self) -> float:
        return round(self.start + self.duration, 3)


class SfxEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["sfx"] = "sfx"
    start: float = Field(ge=0)
    duration: float = Field(gt=0, le=5)
    asset: str
    volume: float = Field(default=0.25, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    query: str | None = None
    reason: str | None = None
    status: Literal["pending", "accepted", "rejected"] = "pending"

    @property
    def end(self) -> float:
        return round(self.start + self.duration, 3)


TimelineEvent = MemeEvent | SfxEvent


class Timeline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    video: str
    events: list[TimelineEvent] = Field(default_factory=list)

    def sorted_events(self) -> list[TimelineEvent]:
        return sorted(self.events, key=lambda e: (e.start, e.id))

    def active_events(self) -> list[TimelineEvent]:
        return [event for event in self.sorted_events() if event.status != "rejected"]


def parse_timeline(data: Any) -> Timeline:
    """Dict → Timeline. Lỗi được dịch sang câu tiếng Việt chỉ đúng chỗ sai."""
    try:
        return Timeline.model_validate(data)
    except ValidationError as e:
        raise TimelineError("Timeline sai định dạng:\n" + format_timeline_error(e)) from None


def load_timeline(path: Path) -> Timeline:
    try:
        data = read_json(path)
    except FileNotFoundError:
        raise TimelineError(f"Không thấy timeline: {path}") from None
    except ValueError as e:  # JSON hỏng
        raise TimelineError(f"{path.name} không phải JSON hợp lệ: {e}") from None
    return parse_timeline(data)


def save_timeline(path: Path, timeline: Timeline) -> Path:
    write_json(path, timeline.model_dump(exclude_none=True))
    return path


def format_timeline_error(e: ValidationError) -> str:
    lines = []
    for err in e.errors():
        loc = list(err["loc"])
        # ('events', 0, 'position') → "sự kiện #0 → position"
        if len(loc) >= 2 and loc[0] == "events":
            duoi = "" if len(loc) < 3 else " → " + ".".join(map(str, loc[2:]))
            cho = f"sự kiện #{loc[1]}{duoi}"
        else:
            cho = ".".join(map(str, loc)) or "(gốc)"
        value = err.get("input")
        shown = "" if isinstance(value, dict) else f" (đang là {value!r})"
        lines.append(f"  - {cho}: {err['msg']}{shown}")
    return "\n".join(lines)
