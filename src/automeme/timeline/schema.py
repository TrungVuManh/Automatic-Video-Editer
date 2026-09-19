"""Định dạng `timeline.json` (SPEC §34) và việc đọc/ghi nó.

Timeline là bản dựng dạng chữ: người sửa được bằng tay rồi render lại mà không tốn lượt AI.
Vì vậy schema chặt (khóa lạ bị báo lỗi) và thông báo lỗi phải nói rõ sai ở đâu.

Timeline hỗ trợ cả overlay `meme` và âm thanh ngắn `sfx`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, ValidationError

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
    # overlay: meme ở góc, video gốc vẫn thấy. cutaway: meme tràn màn hình (SPEC §36) —
    # dành cho punchline mạnh nhất; position/scale bị bỏ qua.
    mode: Literal["overlay", "cutaway"] = "overlay"
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


ZOOM_MIN, ZOOM_MAX = 1.01, 1.5


class ZoomEvent(BaseModel):
    """Zoom nhanh vào khung hình gốc (SPEC §72) — thường đặt ngay trước cú cắt tràn màn hình."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["zoom"] = "zoom"
    start: float = Field(ge=0)
    duration: float = Field(gt=0, le=3)
    factor: float = Field(default=1.1, ge=ZOOM_MIN, le=ZOOM_MAX)
    confidence: float | None = Field(default=None, ge=0, le=1)
    query: str | None = None
    reason: str | None = None
    status: Literal["pending", "accepted", "rejected"] = "pending"

    @property
    def end(self) -> float:
        return round(self.start + self.duration, 3)


LOAI_SU_KIEN = ("meme", "sfx", "zoom")


def _loai_su_kien(value: Any) -> str:
    """Phân loại sự kiện theo khóa `type`. Timeline cũ không ghi `type` → coi là meme.

    Không để pydantic tự thử từng loại: zoom chỉ cần id/start/duration nên một meme thiếu
    `asset` sẽ bị hiểu nhầm thành zoom thay vì báo lỗi.
    """
    if isinstance(value, dict):
        return str(value.get("type", "meme"))
    return str(getattr(value, "type", "meme"))


TimelineEvent = Annotated[
    Annotated[MemeEvent, Tag("meme")]
    | Annotated[SfxEvent, Tag("sfx")]
    | Annotated[ZoomEvent, Tag("zoom")],
    Discriminator(_loai_su_kien),
]


def has_asset(event: TimelineEvent) -> bool:
    """Sự kiện có file đi kèm (meme, SFX). Zoom chỉ biến đổi khung hình gốc nên không có."""
    return not isinstance(event, ZoomEvent)


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
        # ('events', 0, 'sfx', 'position') → "sự kiện #0 (type=sfx) → position"
        if len(loc) >= 2 and loc[0] == "events":
            loai = ""
            if len(loc) >= 3 and loc[2] in LOAI_SU_KIEN:
                loai = f" (type={loc[2]})"
                loc = loc[:2] + loc[3:]
            duoi = "" if len(loc) < 3 else " → " + ".".join(map(str, loc[2:]))
            cho = f"sự kiện #{loc[1]}{loai}{duoi}"
        else:
            cho = ".".join(map(str, loc)) or "(gốc)"
        value = err.get("input")
        shown = "" if isinstance(value, dict) else f" (đang là {value!r})"
        lines.append(f"  - {cho}: {err['msg']}{shown}")
    return "\n".join(lines)
