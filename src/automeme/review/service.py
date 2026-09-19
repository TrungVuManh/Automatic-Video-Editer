"""State và thao tác thuần phía sau giao diện review."""
from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..config import Settings
from ..media.probe import probe
from ..memes.local import SUPPORTED
from ..timeline.schema import (
    SCALE_MAX,
    SCALE_MIN,
    MemeEvent,
    SfxEvent,
    Timeline,
    ViTri,
    has_asset,
    load_timeline,
    save_timeline,
)
from ..timeline.validator import resolve_asset, validate_timeline
from ..utils.files import read_json
from ..workspace import paths_for


class ReviewError(ValueError):
    """Yêu cầu review không hợp lệ hoặc không thể lưu an toàn."""


class EventPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: float | None = Field(default=None, ge=0)
    duration: float | None = Field(default=None, gt=0)
    asset: str | None = Field(default=None, min_length=1)
    position: ViTri | None = None
    scale: float | None = Field(default=None, ge=SCALE_MIN, le=SCALE_MAX)
    volume: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def _khong_cho_patch_rong(self) -> EventPatch:
        if not self.model_fields_set:
            raise ValueError("không có trường nào để cập nhật")
        return self


def apply_event_patch(timeline: Timeline, event_id: str, patch: EventPatch) -> Timeline:
    """Cập nhật một event mà không sửa object đầu vào."""
    result = timeline.model_copy(deep=True)
    for index, event in enumerate(result.events):
        if event.id != event_id:
            continue
        changes = patch.model_dump(exclude_unset=True)
        if isinstance(event, SfxEvent):
            invalid = {"position", "scale"} & changes.keys()
            if invalid:
                raise ReviewError("SFX không có vị trí hoặc tỉ lệ hiển thị.")
            model = SfxEvent
        else:
            if "volume" in changes:
                raise ReviewError("Meme không có âm lượng SFX.")
            model = MemeEvent
        data = event.model_dump()
        data.update(changes)
        result.events[index] = model.model_validate(data)
        return result
    raise ReviewError(f"Không có sự kiện {event_id!r}.")


def set_event_status(timeline: Timeline, event_id: str, status: str) -> Timeline:
    if status not in {"pending", "accepted", "rejected"}:
        raise ReviewError(f"Trạng thái không hợp lệ: {status!r}")
    result = timeline.model_copy(deep=True)
    for event in result.events:
        if event.id == event_id:
            event.status = status
            return result
    raise ReviewError(f"Không có sự kiện {event_id!r}.")


class ReviewSession:
    """Một video/timeline đang được duyệt; mọi ghi file được khóa trong process."""

    def __init__(
        self,
        *,
        video: Path,
        timeline_path: Path,
        settings: Settings,
        output: Path,
        video_duration: float | None,
        render_callback: Callable[[], Path] | None = None,
    ):
        self.video = Path(video)
        self.timeline_path = Path(timeline_path)
        self.settings = settings
        self.output = Path(output)
        self.video_duration = video_duration
        self.render_callback = render_callback
        self._lock = threading.RLock()

    def state(self) -> dict[str, Any]:
        with self._lock:
            timeline = load_timeline(self.timeline_path)
            errors, warnings = self._validate(timeline)
            transcript = self._transcript()
            return {
                "video": self.video.name,
                "timeline": str(self.timeline_path),
                "output": str(self.output),
                "duration": self.video_duration,
                "events": [event.model_dump(mode="json") for event in timeline.sorted_events()],
                "active_count": len(timeline.active_events()),
                "assets": self.available_assets(),
                "sfx_assets": self.available_sfx_assets(),
                "transcript": transcript,
                "errors": errors,
                "warnings": warnings,
            }

    def update(self, event_id: str, patch: EventPatch) -> Timeline:
        with self._lock:
            if "asset" in patch.model_fields_set:
                current = next(
                    (
                        item for item in load_timeline(self.timeline_path).events
                        if item.id == event_id
                    ),
                    None,
                )
                allowed = (
                    self.available_sfx_assets()
                    if isinstance(current, SfxEvent)
                    else self.available_assets()
                )
                if patch.asset is None or patch.asset not in allowed:
                    raise ReviewError(
                        "Asset thay thế phải nằm đúng thư viện meme/GIF hoặc SFX local."
                    )
            timeline = apply_event_patch(load_timeline(self.timeline_path), event_id, patch)
            return self._validate_and_save(timeline)

    def set_status(self, event_id: str, status: str) -> Timeline:
        with self._lock:
            timeline = set_event_status(load_timeline(self.timeline_path), event_id, status)
            return self._validate_and_save(timeline)

    def render(self) -> Path:
        with self._lock:
            if self.render_callback is not None:
                return Path(self.render_callback())
            from ..pipeline import render_timeline

            output, _ = render_timeline(
                self.video,
                self.settings,
                timeline_path=self.timeline_path,
                output=self.output,
                force=True,
            )
            return output

    def event_asset(self, event_id: str) -> Path:
        with self._lock:
            timeline = load_timeline(self.timeline_path)
            event = next((item for item in timeline.events if item.id == event_id), None)
            if event is None:
                raise ReviewError(f"Không có sự kiện {event_id!r}.")
            if not has_asset(event):
                raise ReviewError(f"{event_id} là zoom, không có file để xem trước.")
            path = resolve_asset(
                event.asset,
                self.settings.paths.assets_dir.parent,
                self.settings.paths.assets_dir,
            )
            if not path.is_file():
                raise ReviewError(f"Không thấy asset của {event_id}: {event.asset}")
            return path

    def available_assets(self) -> list[str]:
        root = self.settings.paths.assets_dir.parent.resolve()
        found: list[str] = []
        for directory in (
            self.settings.paths.assets_dir / "memes",
            self.settings.paths.assets_dir / "gifs",
        ):
            if not directory.exists():
                continue
            for path in sorted(directory.rglob("*")):
                supported = path.suffix.casefold() in SUPPORTED
                if path.is_symlink() or not path.is_file() or not supported:
                    continue
                try:
                    found.append(path.resolve().relative_to(root).as_posix())
                except ValueError:
                    continue
        return sorted(set(found))

    def available_sfx_assets(self) -> list[str]:
        root = self.settings.paths.assets_dir.parent.resolve()
        directory = self.settings.paths.assets_dir / "sfx"
        if not directory.exists():
            return []
        found = []
        for path in sorted(directory.rglob("*.ogg")):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                found.append(path.resolve().relative_to(root).as_posix())
            except ValueError:
                continue
        return sorted(set(found))

    def _validate_and_save(self, timeline: Timeline) -> Timeline:
        errors, _ = self._validate(timeline)
        if errors:
            raise ReviewError("Timeline chưa thể lưu:\n" + "\n".join(f"- {e}" for e in errors))
        save_timeline(self.timeline_path, timeline)
        return timeline

    def _validate(self, timeline: Timeline) -> tuple[list[str], list[str]]:
        root = self.settings.paths.assets_dir.parent
        asset_paths = {
            event.asset: resolve_asset(event.asset, root, self.settings.paths.assets_dir)
            for event in timeline.active_events() if has_asset(event)
        }
        return validate_timeline(
            timeline,
            video_duration=self.video_duration,
            asset_paths=asset_paths,
            meme_cfg=self.settings.meme,
            editing_cfg=self.settings.editing,
        )

    def _transcript(self) -> list[dict[str, Any]]:
        path = paths_for(self.video, self.settings).transcript
        try:
            data = read_json(path)
        except (FileNotFoundError, OSError, ValueError):
            return []
        rows = data.get("segments") if isinstance(data, dict) else None
        return rows if isinstance(rows, list) else []


def create_review_session(
    video: Path,
    settings: Settings,
    *,
    timeline_path: Path | None = None,
    output: Path | None = None,
    render_callback: Callable[[], Path] | None = None,
) -> ReviewSession:
    video = Path(video).expanduser()
    if not video.is_file():
        raise FileNotFoundError(f"Không thấy video: {video}")
    paths = paths_for(video, settings)
    timeline = Path(timeline_path) if timeline_path else paths.timeline
    if not timeline.is_file():
        raise FileNotFoundError(
            f"Chưa có timeline {timeline}. Chạy `automeme run {video}` trước."
        )
    # Đọc sớm để CLI báo schema hỏng trước khi mở trình duyệt.
    load_timeline(timeline)
    duration = probe(video).duration
    return ReviewSession(
        video=video,
        timeline_path=timeline,
        settings=settings,
        output=Path(output) if output else paths.output,
        video_duration=duration,
        render_callback=render_callback,
    )
