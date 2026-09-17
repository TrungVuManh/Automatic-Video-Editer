"""Cài và tìm bộ sound effect Kenney CC0 đã gắn nhãn Việt–Anh."""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from ..config import Settings
from ..memes.matching import match_score
from ..memes.popular import InstallResult
from ..utils.files import read_json
from ..utils.logger import log
from .schema import SfxCandidate

CATALOG_PATH = Path(__file__).with_name("catalog") / "popular_kenney.json"
PINNED_REVISION = "fa851a79288bf0ee81cdf6faa9430bbbed48b292"
RAW_PREFIX = (
    "https://raw.githubusercontent.com/chenisan/AudioSFX/"
    f"{PINNED_REVISION}/assets/sfx-library/files/"
)
ALLOWED_HOST = "raw.githubusercontent.com"
ALLOWED_PATH_PREFIX = f"/chenisan/AudioSFX/{PINNED_REVISION}/assets/sfx-library/files/"
MAX_SFX_BYTES = 5 * 1024 * 1024


class CatalogSfx(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    file: str = Field(pattern=r"^[A-Za-z0-9_]+\.ogg$")
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    tags: list[str] = Field(min_length=2)
    emotion: list[str] = Field(default_factory=list)
    style: list[str] = Field(default_factory=list)
    description: str = Field(min_length=10)
    duration: float = Field(gt=0, le=5)
    intensity: float = Field(ge=0, le=1)
    quality: float = Field(ge=0, le=1)
    recommended_volume: float = Field(ge=0, le=1)


def load_sfx_catalog(path: Path = CATALOG_PATH) -> list[CatalogSfx]:
    rows = read_json(path)
    if not isinstance(rows, list):
        raise ValueError("Catalog SFX phải là một mảng JSON.")
    items = [CatalogSfx.model_validate(row) for row in rows]
    ids = [item.id for item in items]
    files = [item.file for item in items]
    if len(ids) != len(set(ids)) or len(files) != len(set(files)):
        raise ValueError("Catalog SFX có id hoặc file bị trùng.")
    return items


def parse_sfx_library(text: str) -> tuple[list[SfxCandidate], list[str]]:
    items: list[SfxCandidate] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for line_no, raw in enumerate(text.splitlines(), 1):
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        try:
            item = SfxCandidate.model_validate(json.loads(raw))
            if item.id in seen:
                raise ValueError(f"trùng id {item.id!r}")
            seen.add(item.id)
            items.append(item)
        except (ValueError, TypeError) as exc:
            warnings.append(f"sfx library dòng {line_no}: {exc}")
    return items, warnings


def upsert_sfx_candidates(path: Path, items: list[SfxCandidate]) -> None:
    existing, _ = parse_sfx_library(path.read_text(encoding="utf-8")) if path.exists() else ([], [])
    merged = {item.id: item for item in existing}
    merged.update({item.id: item for item in items})
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    lines = [
        json.dumps(item.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
        for item in sorted(merged.values(), key=lambda row: row.id)
    ]
    part.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    part.replace(path)


class LocalSfxProvider:
    def __init__(self, *, library_file: Path, project_root: Path):
        self.library_file = Path(library_file)
        self.project_root = Path(project_root)
        self._items: list[SfxCandidate] | None = None

    def search(self, query: str, limit: int = 10) -> list[SfxCandidate]:
        scored: list[SfxCandidate] = []
        for item in self._load():
            if not item.safe:
                continue
            score = match_score(query, [item.id, item.description, *item.tags,
                                        *item.emotion, *item.style])
            if score <= 0:
                continue
            scored.append(item.model_copy(update={"semantic_score": score}))
        return sorted(
            scored, key=lambda item: (-item.semantic_score, -item.quality, item.id)
        )[:limit]

    def materialize(self, item: SfxCandidate) -> Path:
        path = Path(item.filename).expanduser()
        attempts = [path] if path.is_absolute() else [
            self.project_root / path,
            self.library_file.parent / path,
        ]
        for attempt in attempts:
            resolved = attempt.resolve()
            if resolved.is_file():
                return resolved
        raise FileNotFoundError(f"Không thấy file local của SFX {item.id}: {item.filename}")

    def _load(self) -> list[SfxCandidate]:
        if self._items is None:
            if not self.library_file.exists():
                self._items = []
            else:
                self._items, warnings = parse_sfx_library(
                    self.library_file.read_text(encoding="utf-8")
                )
                for warning in warnings:
                    log.warning("%s", warning)
        return self._items


def install_popular_sfx(
    settings: Settings,
    *,
    limit: int = 30,
    catalog_path: Path = CATALOG_PATH,
    client_factory: Callable[..., Any] | None = None,
) -> InstallResult:
    if not 1 <= limit <= 30:
        raise ValueError("Số SFX cần cài phải nằm trong khoảng 1–30.")
    catalog = load_sfx_catalog(catalog_path)[:limit]
    root = settings.paths.assets_dir.parent.resolve()
    target_dir = settings.paths.assets_dir / "sfx" / "popular"
    target_dir.mkdir(parents=True, exist_ok=True)
    client = _client(client_factory)
    installed = reused = 0
    errors: list[str] = []
    candidates: list[SfxCandidate] = []
    try:
        for item in catalog:
            output = target_dir / item.file
            url = RAW_PREFIX + item.file
            try:
                if output.is_file() and output.read_bytes()[:4] == b"OggS":
                    reused += 1
                else:
                    output.unlink(missing_ok=True)
                    _download_sfx(client, url, output)
                    installed += 1
                candidates.append(_to_candidate(item, output, root, url))
            except Exception as exc:
                output.with_name(output.name + ".part").unlink(missing_ok=True)
                errors.append(f"{item.title}: {exc}")
                log.warning("Không cài được SFX %s: %s", item.id, exc)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
    upsert_sfx_candidates(settings.sfx.library_file, candidates)
    return InstallResult(
        total=len(catalog), installed=installed, reused=reused,
        failed=len(errors), errors=errors,
    )


def _client(factory: Callable[..., Any] | None):
    if factory is not None:
        return factory(timeout=30, follow_redirects=False)
    import httpx

    return httpx.Client(timeout=30, follow_redirects=False)


def _download_sfx(client: Any, url: str, output: Path) -> None:
    _validate_sfx_url(url)
    part = output.with_name(output.name + ".part")
    part.unlink(missing_ok=True)
    with client.stream("GET", url) as response:
        if 300 <= response.status_code < 400:
            raise ValueError("nguồn trả redirect")
        response.raise_for_status()
        mime = response.headers.get("content-type", "").split(";", 1)[0].casefold()
        if mime not in {"audio/ogg", "application/ogg", "application/octet-stream"}:
            raise ValueError(f"MIME không hỗ trợ: {mime or '?'}")
        declared = response.headers.get("content-length")
        if declared and int(declared) > MAX_SFX_BYTES:
            raise ValueError("file vượt giới hạn 5 MB")
        size = 0
        with open(part, "xb") as handle:
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_SFX_BYTES:
                    raise ValueError("file vượt giới hạn khi đang tải")
                handle.write(chunk)
        if size < 4 or part.read_bytes()[:4] != b"OggS":
            raise ValueError("file không phải OGG hợp lệ")
    part.replace(output)


def _validate_sfx_url(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname.casefold() if parsed.hostname else ""
    if (
        parsed.scheme.casefold() != "https"
        or host != ALLOWED_HOST
        or parsed.username
        or not parsed.path.startswith(ALLOWED_PATH_PREFIX)
        or not parsed.path.endswith(".ogg")
    ):
        raise ValueError("URL SFX phải là file OGG từ revision GitHub đã ghim")


def _to_candidate(item: CatalogSfx, output: Path, root: Path, url: str) -> SfxCandidate:
    return SfxCandidate(
        id=f"kenney-{item.id}",
        filename=output.resolve().relative_to(root).as_posix(),
        tags=item.tags,
        emotion=item.emotion,
        style=item.style,
        description=item.description,
        intensity=item.intensity,
        quality=item.quality,
        duration=item.duration,
        recommended_volume=item.recommended_volume,
        source_url=url,
        license_note="CC0 1.0 — Kenney Interface/Impact/Digital Sounds; không bắt buộc ghi công.",
    )
