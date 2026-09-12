"""State và nghiệp vụ phía sau AutoMeme Studio.

Module này không phụ thuộc HTTP để các quy tắc upload, hàng đợi và metadata có thể test độc lập.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, BinaryIO, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..config import Settings, list_profiles, load_settings
from ..doctor import check_environment
from ..memes.local import SUPPORTED, media_type, upsert_library_candidates
from ..memes.schema import MemeCandidate
from ..review.service import ReviewSession, create_review_session
from ..utils.files import CONFIGS_DIR
from ..workspace import paths_for, slug

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
MAX_VIDEO_BYTES = 10 * 1024**3
MAX_ASSET_BYTES = 100 * 1024**2
COPY_CHUNK = 1024 * 1024


class StudioError(ValueError):
    """Yêu cầu từ Studio không hợp lệ hoặc không thể thực hiện an toàn."""


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video: str = Field(min_length=1)
    profile: str = "default"
    force: bool = False


class MetadataPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    emotion: list[str] = Field(default_factory=list)
    style: list[str] = Field(default_factory=list)
    description: str = ""
    intensity: float = Field(default=0.5, ge=0, le=1)
    quality: float = Field(default=0.5, ge=0, le=1)
    safe: bool = True
    language: str = "none"


class JobState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    video: str
    profile: str
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    stage: str = "waiting"
    completed_stages: list[str] = Field(default_factory=list)
    message: str = "Đang chờ bắt đầu"
    output: str | None = None
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None


PipelineRunner = Callable[
    [Path, Settings, bool, Callable[[str, str], None]], tuple[Path, Any]
]


class StudioService:
    """Workspace và một hàng đợi pipeline đơn cho giao diện local."""

    def __init__(
        self,
        settings: Settings,
        *,
        settings_loader: Callable[[str | None], Settings] | None = None,
        runner: PipelineRunner | None = None,
        profiles_dir: Path = CONFIGS_DIR,
        environment_checker: Callable[[Settings], list[tuple[str, str, str]]] | None = None,
    ):
        self.settings = settings
        self._settings_loader = settings_loader or (lambda profile: load_settings(profile))
        self._runner = runner or self._run_pipeline
        self.profiles_dir = Path(profiles_dir)
        self._environment_checker = environment_checker or (
            lambda active: check_environment(active)
        )
        self._job_lock = threading.RLock()
        self._library_lock = threading.RLock()
        self._active_thread: threading.Thread | None = None
        self._job: JobState | None = None
        self._environment: list[tuple[str, str, str]] | None = None
        self._reviews: dict[str, ReviewSession] = {}

    def dashboard(self, *, refresh_environment: bool = False) -> dict[str, Any]:
        projects = self.projects()
        return {
            "app": "AutoMeme Studio",
            "profiles": ["default", *list_profiles(self.profiles_dir)],
            "projects": projects,
            "project_count": len(projects),
            "asset_count": len(self.library()),
            "environment": self.environment(refresh=refresh_environment),
            "job": self.job(),
        }

    def environment(self, *, refresh: bool = False) -> list[dict[str, str]]:
        if self._environment is None or refresh:
            self._environment = self._environment_checker(self.settings)
        return [
            {"name": name, "status": status, "detail": detail}
            for name, status, detail in self._environment
        ]

    def projects(self) -> list[dict[str, Any]]:
        input_dir = self.settings.paths.data_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        for video in input_dir.iterdir():
            if (
                video.is_symlink()
                or not video.is_file()
                or video.suffix.casefold() not in VIDEO_EXTENSIONS
            ):
                continue
            paths = paths_for(video, self.settings)
            artifacts = {
                "transcript": paths.transcript.is_file(),
                "analysis": paths.analysis.is_file(),
                "timeline": paths.timeline.is_file(),
                "output": paths.output.is_file(),
            }
            if artifacts["output"]:
                status = "completed"
            elif artifacts["timeline"]:
                status = "review"
            elif any(artifacts.values()):
                status = "processing"
            else:
                status = "new"
            stat = video.stat()
            rows.append({
                "name": video.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "status": status,
                "artifacts": artifacts,
            })
        return sorted(rows, key=lambda row: (-row["modified"], row["name"].casefold()))

    def upload_video(self, filename: str, stream: BinaryIO, length: int) -> dict[str, Any]:
        target = self._upload(
            filename,
            stream,
            length,
            directory=self.settings.paths.data_dir / "input",
            extensions=VIDEO_EXTENSIONS,
            max_bytes=MAX_VIDEO_BYTES,
            label="video",
        )
        return next(row for row in self.projects() if row["name"] == target.name)

    def upload_asset(self, filename: str, stream: BinaryIO, length: int) -> MemeCandidate:
        suffix = Path(filename).suffix.casefold()
        directory = self.settings.paths.assets_dir / ("gifs" if suffix == ".gif" else "memes")
        target = self._upload(
            filename,
            stream,
            length,
            directory=directory,
            extensions=SUPPORTED,
            max_bytes=MAX_ASSET_BYTES,
            label="meme",
        )
        root = self.settings.paths.assets_dir.parent
        try:
            relative = target.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            relative = str(target.resolve())
        item = MemeCandidate(
            id=self._unique_library_id(slug(target.stem)),
            filename=relative,
            type=media_type(target),
            tags=[part for part in slug(target.stem).split("-") if part],
        )
        self._upsert_candidate(item)
        return item

    def library(self) -> list[dict[str, Any]]:
        from ..memes.local import LocalMemeProvider
        from ..sfx.library import LocalSfxProvider

        provider = LocalMemeProvider(
            library_file=self.settings.meme.library_file,
            asset_dirs=[
                self.settings.paths.assets_dir / "memes",
                self.settings.paths.assets_dir / "gifs",
            ],
            project_root=self.settings.paths.assets_dir.parent,
        )
        rows = []
        for item in provider._load():
            data = item.model_dump(mode="json")
            data["preview_url"] = "/media/library?id=" + item.id
            rows.append(data)
        sound_provider = LocalSfxProvider(
            library_file=self.settings.sfx.library_file,
            project_root=self.settings.paths.assets_dir.parent,
        )
        for item in sound_provider._load():
            data = item.model_dump(mode="json")
            data["preview_url"] = "/media/library?id=" + item.id
            rows.append(data)
        return sorted(rows, key=lambda item: item["id"].casefold())

    def library_asset(self, item_id: str) -> Path:
        item = next((row for row in self.library() if row["id"] == item_id), None)
        if item is None:
            raise StudioError(f"Không có asset {item_id!r}.")
        root = self.settings.paths.assets_dir.parent
        path = Path(item["filename"])
        attempts = [path] if path.is_absolute() else [
            root / path,
            self.settings.meme.library_file.parent / path,
            self.settings.paths.assets_dir / "memes" / path,
            self.settings.paths.assets_dir / "gifs" / path,
            self.settings.paths.assets_dir / "sfx" / path,
        ]
        for attempt in attempts:
            resolved = attempt.resolve()
            try:
                resolved.relative_to(self.settings.paths.assets_dir.resolve())
            except ValueError:
                continue
            if resolved.is_file() and not resolved.is_symlink():
                return resolved
        raise FileNotFoundError(f"Không thấy file của meme {item_id!r}.")

    def update_metadata(self, item_id: str, patch: MetadataPatch) -> MemeCandidate:
        if patch.id != item_id:
            raise StudioError("ID trong URL và nội dung không khớp.")
        existing = next((row for row in self.library() if row["id"] == item_id), None)
        if existing is None:
            raise StudioError(f"Không có meme {item_id!r}.")
        if existing.get("type") == "audio":
            raise StudioError("Metadata SFX mặc định là chỉ đọc để giữ catalog CC0 nhất quán.")
        candidate = MemeCandidate.model_validate({
            **{key: value for key, value in existing.items() if key != "preview_url"},
            **patch.model_dump(),
        })
        self._upsert_candidate(candidate)
        return candidate

    def install_popular_library(self, *, limit: int = 100) -> dict[str, Any]:
        from ..memes.popular import install_popular_memes

        with self._library_lock:
            result = install_popular_memes(self.settings, limit=limit)
        return result.model_dump(mode="json")

    def install_animated_library(self, *, limit: int = 30) -> dict[str, Any]:
        from ..memes.animated import install_animated_gifs

        with self._library_lock:
            result = install_animated_gifs(self.settings, limit=limit)
        return result.model_dump(mode="json")

    def install_sfx_library(self, *, limit: int = 30) -> dict[str, Any]:
        from ..sfx.library import install_popular_sfx

        with self._library_lock:
            result = install_popular_sfx(self.settings, limit=limit)
        return result.model_dump(mode="json")

    def start_job(self, request: JobRequest) -> dict[str, Any]:
        video = self.video_path(request.video)
        with self._job_lock:
            if self._active_thread is not None and self._active_thread.is_alive():
                raise StudioError("Đang có một video được xử lý. Hãy chờ job hiện tại hoàn tất.")
            self._job = JobState(
                id=uuid.uuid4().hex[:12],
                video=video.name,
                profile=request.profile,
            )
            thread = threading.Thread(
                target=self._execute_job,
                args=(video, request),
                name=f"automeme-{self._job.id}",
                daemon=True,
            )
            self._active_thread = thread
            thread.start()
            return self.job() or {}

    def job(self) -> dict[str, Any] | None:
        with self._job_lock:
            return self._job.model_dump(mode="json") if self._job else None

    def review(self, video_name: str) -> ReviewSession:
        with self._job_lock:
            session = self._reviews.get(video_name)
            if session is None:
                session = create_review_session(self.video_path(video_name), self.settings)
                self._reviews[video_name] = session
            return session

    def video_path(self, video_name: str) -> Path:
        if Path(video_name).name != video_name:
            raise StudioError("Tên video không hợp lệ.")
        path = (self.settings.paths.data_dir / "input" / video_name).resolve()
        root = (self.settings.paths.data_dir / "input").resolve()
        if path.parent != root or not path.is_file() or path.is_symlink():
            raise FileNotFoundError(f"Không thấy video: {video_name}")
        if path.suffix.casefold() not in VIDEO_EXTENSIONS:
            raise StudioError("Định dạng video không được hỗ trợ.")
        return path

    def output_path(self, video_name: str) -> Path:
        output = paths_for(self.video_path(video_name), self.settings).output
        if not output.is_file():
            raise FileNotFoundError("Video output chưa được render.")
        return output

    def _execute_job(self, video: Path, request: JobRequest) -> None:
        with self._job_lock:
            assert self._job is not None
            self._job.status = "running"
            self._job.started_at = time.time()
            self._job.message = "Đang chuẩn bị pipeline"

        def progress(stage: str, state: str) -> None:
            with self._job_lock:
                assert self._job is not None
                self._job.stage = stage
                self._job.message = _stage_message(stage, state)
                if state == "completed" and stage not in self._job.completed_stages:
                    self._job.completed_stages.append(stage)

        try:
            profile = None if request.profile == "default" else request.profile
            active = self._settings_loader(profile)
            output, _ = self._runner(video, active, request.force, progress)
            with self._job_lock:
                assert self._job is not None
                self._job.status = "completed"
                self._job.stage = "completed"
                self._job.message = "Video đã sẵn sàng"
                self._job.output = str(output)
                self._job.finished_at = time.time()
        except Exception as exc:  # lỗi được trình bày trong UI, log đầy đủ ở runner
            with self._job_lock:
                assert self._job is not None
                self._job.status = "failed"
                self._job.message = "Pipeline đã dừng"
                self._job.error = str(exc)
                self._job.finished_at = time.time()

    @staticmethod
    def _run_pipeline(
        video: Path,
        settings: Settings,
        force: bool,
        progress: Callable[[str, str], None],
    ) -> tuple[Path, Any]:
        from ..pipeline import run_video

        return run_video(video, settings, force=force, progress_callback=progress)

    @staticmethod
    def _upload(
        filename: str,
        stream: BinaryIO,
        length: int,
        *,
        directory: Path,
        extensions: set[str],
        max_bytes: int,
        label: str,
    ) -> Path:
        raw = Path(filename)
        if not filename or raw.name != filename or filename in {".", ".."}:
            raise StudioError(f"Tên file {label} không hợp lệ.")
        suffix = raw.suffix.casefold()
        if suffix not in extensions:
            allowed = ", ".join(sorted(extensions))
            raise StudioError(f"Định dạng {label} không hỗ trợ. Cho phép: {allowed}.")
        if length <= 0 or length > max_bytes:
            raise StudioError(f"Dung lượng {label} không hợp lệ hoặc vượt giới hạn.")
        directory.mkdir(parents=True, exist_ok=True)
        stem = slug(raw.stem)
        target = directory / f"{stem}{suffix}"
        number = 2
        while target.exists() or target.with_name(target.name + ".part").exists():
            target = directory / f"{stem}-{number}{suffix}"
            number += 1
        part = target.with_name(target.name + ".part")
        remaining = length
        try:
            with open(part, "xb") as handle:
                while remaining:
                    chunk = stream.read(min(COPY_CHUNK, remaining))
                    if not chunk:
                        raise StudioError(f"Dữ liệu {label} bị thiếu.")
                    handle.write(chunk)
                    remaining -= len(chunk)
            part.replace(target)
        except Exception:
            part.unlink(missing_ok=True)
            raise
        return target

    def _unique_library_id(self, base: str) -> str:
        existing = {row["id"] for row in self.library()}
        candidate, number = base or "meme", 2
        while candidate in existing:
            candidate = f"{base}-{number}"
            number += 1
        return candidate

    def _upsert_candidate(self, item: MemeCandidate) -> None:
        with self._library_lock:
            upsert_library_candidates(self.settings.meme.library_file, [item])


def _stage_message(stage: str, state: str) -> str:
    names = {
        "transcribe": "Nhận dạng lời thoại",
        "analyze": "Phân tích khoảnh khắc",
        "timeline": "Chọn và xếp meme",
        "render": "Dựng video",
    }
    action = "Đã xong" if state == "completed" else "Đang"
    return f"{action} {names.get(stage, stage).lower()}"
