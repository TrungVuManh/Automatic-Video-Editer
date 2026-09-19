"""State và thao tác thuần phía sau giao diện review."""
from __future__ import annotations

import re
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..config import Settings
from ..media.probe import probe
from ..memes.local import SUPPORTED
from ..memes.schema import MemeCandidate
from ..timeline.schema import (
    SCALE_MAX,
    SCALE_MIN,
    ZOOM_MAX,
    ZOOM_MIN,
    MemeEvent,
    SfxEvent,
    Timeline,
    ViTri,
    ZoomEvent,
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
    mode: Literal["overlay", "cutaway"] | None = None
    factor: float | None = Field(default=None, ge=ZOOM_MIN, le=ZOOM_MAX)

    @model_validator(mode="after")
    def _khong_cho_patch_rong(self) -> EventPatch:
        if not self.model_fields_set:
            raise ValueError("không có trường nào để cập nhật")
        return self


class AddMemePayload(BaseModel):
    """Body của yêu cầu thêm meme từ giao diện duyệt."""

    model_config = ConfigDict(extra="forbid")

    start: float = Field(ge=0)
    asset: str = Field(min_length=1)
    mode: Literal["overlay", "cutaway"] = "overlay"


def apply_event_patch(timeline: Timeline, event_id: str, patch: EventPatch) -> Timeline:
    """Cập nhật một event mà không sửa object đầu vào."""
    result = timeline.model_copy(deep=True)
    for index, event in enumerate(result.events):
        if event.id != event_id:
            continue
        changes = patch.model_dump(exclude_unset=True)
        if isinstance(event, SfxEvent):
            if {"position", "scale", "mode", "factor"} & changes.keys():
                raise ReviewError("SFX chỉ sửa được file, thời gian và âm lượng.")
            model: type[MemeEvent | SfxEvent | ZoomEvent] = SfxEvent
        elif isinstance(event, ZoomEvent):
            if {"asset", "position", "scale", "volume", "mode"} & changes.keys():
                raise ReviewError("Zoom chỉ sửa được thời gian và độ phóng.")
            model = ZoomEvent
        else:
            if {"volume", "factor"} & changes.keys():
                raise ReviewError("Meme không có âm lượng SFX hay độ phóng zoom.")
            model = MemeEvent
        data = event.model_dump()
        data.update(changes)
        result.events[index] = model.model_validate(data)
        return result
    raise ReviewError(f"Không có sự kiện {event_id!r}.")


def add_meme_event(timeline: Timeline, *, start: float, duration: float, asset: str,
                   mode: Literal["overlay", "cutaway"] = "overlay") -> tuple[Timeline, str]:
    """Thêm meme do người duyệt chọn (đã chấp nhận sẵn); trả timeline mới và id sự kiện mới."""
    result = timeline.model_copy(deep=True)
    event_id = new_event_id(result)
    result.events.append(MemeEvent(
        id=event_id, start=round(start, 3), duration=round(duration, 3), asset=asset,
        mode=mode, status="accepted", reason="người duyệt thêm",
    ))
    return result, event_id


def new_event_id(timeline: Timeline) -> str:
    """`event_NNN` lớn hơn mọi id dạng số đang có, để không trùng cả với sự kiện đã từ chối."""
    so = [int(m.group(1)) for e in timeline.events if (m := re.fullmatch(r"event_(\d+)", e.id))]
    return f"event_{max(so, default=0) + 1:03d}"


def rank_suggestions(candidates: Sequence[MemeCandidate], *, exclude_styles: Sequence[str] = (),
                     animated_first: bool = False, limit: int = 8) -> list[MemeCandidate]:
    """Xếp hạng meme thay thế cho người duyệt. Hàm thuần.

    Điểm = 0.8 × khớp nghĩa + 0.2 × chất lượng; cú cắt tràn màn hình cộng thêm 0.1 cho GIF/video
    (cần chuyển động). Bỏ asset không an toàn và style bị loại (`meme.exclude_styles`).
    """
    loai = set(exclude_styles)

    def diem(c: MemeCandidate) -> float:
        dong = 0.1 if animated_first and c.type in ("gif", "video") else 0.0
        return 0.8 * c.semantic_score + 0.2 * c.quality + dong

    hop_le = [c for c in candidates if c.safe and not loai & set(c.style)]
    return sorted(hop_le, key=lambda c: (-diem(c), c.id))[:limit]


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
                # để bản xem trước trên web khớp bản render (configs/, mục meme)
                "display": self.settings.meme.model_dump(mode="json", include={
                    "scale_default", "position_default", "margin_ratio", "max_height_ratio"}),
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

    def add_meme(self, *, start: float, asset: str,
                 mode: Literal["overlay", "cutaway"] = "overlay",
                 duration: float | None = None) -> tuple[Timeline, str]:
        """Người duyệt tự chèn meme từ thư viện local; ràng buộc cứng vẫn do validator quyết."""
        with self._lock:
            if asset not in self.available_assets():
                raise ReviewError("Meme thêm vào phải nằm trong thư viện meme/GIF local.")
            if duration is None:
                cfg = self.settings.cutaway if mode == "cutaway" else self.settings.meme
                duration = cfg.duration_min
            if self.video_duration is not None:
                duration = min(duration, self.video_duration - start)
            if duration <= 0:
                raise ReviewError("Điểm chèn nằm ngoài video.")
            timeline, event_id = add_meme_event(
                load_timeline(self.timeline_path), start=start, duration=duration,
                asset=asset, mode=mode,
            )
            return self._validate_and_save(timeline), event_id

    def suggestions(self, event_id: str | None, query: str | None = None, limit: int = 8,
                    mode: Literal["overlay", "cutaway"] | None = None) -> list[dict[str, Any]]:
        """Meme local thay thế cho một sự kiện meme, xếp hạng theo truy vấn của sự kiện
        (hoặc `query` người duyệt gõ). `event_id=None`: tìm meme để chèn mới. Chỉ trả asset
        nằm trong thư viện được phép chọn."""
        from ..memes.base import MemeProviderError
        from ..memes.local import LocalMemeProvider

        with self._lock:
            event = None
            if event_id is not None:
                timeline = load_timeline(self.timeline_path)
                event = next((item for item in timeline.events if item.id == event_id), None)
                if not isinstance(event, MemeEvent):
                    raise ReviewError(f"{event_id} không phải meme — không có gợi ý thay thế.")
            provider = LocalMemeProvider(
                library_file=self.settings.meme.library_file,
                asset_dirs=[self.settings.paths.assets_dir / "memes",
                            self.settings.paths.assets_dir / "gifs"],
                project_root=self.settings.paths.assets_dir.parent,
            )
            text = (query or "").strip() or (event and (event.query or event.reason)) or ""
            candidates = provider.search(text, limit * 4) if text else []
            if not (query or "").strip():
                # Truy vấn của AI thường chỉ khớp vài meme: bù phần còn lại của thư viện (điểm
                # khớp 0 nên luôn đứng sau) để người duyệt luôn có đủ lựa chọn. Người duyệt tự gõ
                # từ khóa thì chỉ hiện kết quả khớp.
                seen = {c.id for c in candidates}
                candidates = candidates + [c for c in provider._load()
                                           if c.safe and c.id not in seen]
            ranked = rank_suggestions(
                candidates, exclude_styles=self.settings.meme.exclude_styles,
                animated_first=(mode or (event and event.mode)) == "cutaway",
                limit=limit * 2,
            )
            allowed = set(self.available_assets())
            root = self.settings.paths.assets_dir.parent.resolve()
            rows: list[dict[str, Any]] = []
            for candidate in ranked:
                try:
                    asset = provider.materialize(candidate).relative_to(root).as_posix()
                except (MemeProviderError, ValueError):
                    continue
                if asset not in allowed:
                    continue
                rows.append({
                    "asset": asset,
                    "id": candidate.id,
                    "type": candidate.type,
                    "description": candidate.description,
                    "tags": candidate.tags[:4],
                    "score": round(candidate.semantic_score, 3),
                    "current": event is not None and asset == event.asset,
                })
                if len(rows) >= limit:
                    break
            return rows

    def asset_file(self, asset: str) -> Path:
        """File của một asset trong thư viện được phép (xem trước gợi ý); chặn đường dẫn lạ."""
        if asset not in self.available_assets() and asset not in self.available_sfx_assets():
            raise ReviewError("Asset không nằm trong thư viện local.")
        return resolve_asset(asset, self.settings.paths.assets_dir.parent,
                             self.settings.paths.assets_dir)

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
