"""Cài bộ reaction GIF động đã gắn nhãn ngữ nghĩa Việt–Anh."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from ..config import Settings
from ..utils.files import read_json
from ..utils.logger import log
from ..workspace import slug
from .local import tokenize, upsert_library_candidates
from .popular import SEMANTICS, InstallResult
from .schema import MemeCandidate

CATALOG_PATH = Path(__file__).with_name("catalog") / "popular_gifs.json"
RAW_GITHUB_HOST = "raw.githubusercontent.com"
MAX_GIF_BYTES = 15 * 1024 * 1024
TRUSTED_REVISIONS = {
    ("cheesits456", "ReactionPics"): "71198656520247573b8109f664d7051b378f9444",
    ("snipe", "animated-gifs"): "d5ff840d028c2438497e7a7709d6bb9d5f7c6d68",
}


class AnimatedTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gif_id: str = Field(pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1)
    url: HttpUrl
    labels: list[str] = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    description: str = Field(min_length=10)
    quality: float = Field(ge=0, le=1)
    safe: bool = True


def load_animated_catalog(path: Path = CATALOG_PATH) -> list[AnimatedTemplate]:
    rows = read_json(path)
    if not isinstance(rows, list):
        raise ValueError("Catalog GIF động phải là một mảng JSON.")
    templates = [AnimatedTemplate.model_validate(row) for row in rows]
    ids = [item.gif_id for item in templates]
    if len(ids) != len(set(ids)):
        raise ValueError("Catalog GIF động có gif_id bị trùng.")
    unknown = sorted({label for item in templates for label in item.labels} - set(SEMANTICS))
    if unknown:
        raise ValueError("Catalog GIF có semantic label chưa định nghĩa: " + ", ".join(unknown))
    for item in templates:
        _validate_github_url(str(item.url))
    return templates


def install_animated_gifs(
    settings: Settings,
    *,
    limit: int = 30,
    catalog_path: Path = CATALOG_PATH,
    client_factory: Callable[..., Any] | None = None,
) -> InstallResult:
    """Tải tối đa `limit` GIF đã kiểm tra có ít nhất hai frame."""
    if not 1 <= limit <= 30:
        raise ValueError("Số GIF cần cài phải nằm trong khoảng 1–30.")
    catalog = load_animated_catalog(catalog_path)[:limit]
    project_root = settings.paths.assets_dir.parent.resolve()
    target_dir = settings.paths.assets_dir / "gifs" / "popular"
    target_dir.mkdir(parents=True, exist_ok=True)
    client = _client(client_factory)
    installed = reused = 0
    errors: list[str] = []
    candidates: list[MemeCandidate] = []
    try:
        for item in catalog:
            output = target_dir / f"{slug(item.name)}-{item.gif_id}.gif"
            try:
                if output.is_file() and gif_frame_count(output.read_bytes()) >= 2:
                    reused += 1
                else:
                    output.unlink(missing_ok=True)
                    _download_gif(client, str(item.url), output)
                    installed += 1
                candidates.append(_to_candidate(item, output, project_root))
            except Exception as exc:
                output.with_name(output.name + ".part").unlink(missing_ok=True)
                message = f"{item.name}: {exc}"
                errors.append(message)
                log.warning("Không cài được GIF phổ biến %s", message)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
    upsert_library_candidates(settings.meme.library_file, candidates)
    return InstallResult(
        total=len(catalog),
        installed=installed,
        reused=reused,
        failed=len(errors),
        errors=errors,
    )


def _client(factory: Callable[..., Any] | None):
    if factory is not None:
        return factory(timeout=30, follow_redirects=False)
    import httpx

    return httpx.Client(timeout=30, follow_redirects=False)


def _download_gif(client: Any, url: str, output: Path) -> None:
    _validate_github_url(url)
    part = output.with_name(output.name + ".part")
    part.unlink(missing_ok=True)
    with client.stream("GET", url) as response:
        if 300 <= response.status_code < 400:
            raise ValueError("nguồn trả redirect")
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";", 1)[0].casefold()
        if content_type != "image/gif":
            raise ValueError(f"MIME không phải GIF: {content_type or '?'}")
        declared = response.headers.get("content-length")
        if declared and int(declared) > MAX_GIF_BYTES:
            raise ValueError("file vượt giới hạn 15 MB")
        size = 0
        with open(part, "xb") as handle:
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_GIF_BYTES:
                    raise ValueError("file vượt giới hạn khi đang tải")
                handle.write(chunk)
        if gif_frame_count(part.read_bytes()) < 2:
            raise ValueError("file không phải GIF động nhiều frame")
    part.replace(output)


def _validate_github_url(url: str) -> None:
    parsed = urlparse(url)
    hostname = parsed.hostname.casefold() if parsed.hostname else ""
    parts = parsed.path.lstrip("/").split("/")
    if (
        parsed.scheme.casefold() != "https"
        or hostname != RAW_GITHUB_HOST
        or parsed.username
        or len(parts) < 4
        or not parts[-1].casefold().endswith(".gif")
    ):
        raise ValueError("URL GIF phải là HTTPS raw.githubusercontent.com đã ghim commit")
    owner, repository, revision = parts[:3]
    expected = TRUSTED_REVISIONS.get((owner, repository))
    if expected is None or revision != expected:
        raise ValueError("repository hoặc revision GIF không nằm trong allowlist")


def gif_frame_count(data: bytes) -> int:
    """Đếm image descriptor trong GIF mà không cần Pillow."""
    if len(data) < 14 or data[:6] not in {b"GIF87a", b"GIF89a"}:
        raise ValueError("header GIF không hợp lệ")
    position = 13
    packed = data[10]
    if packed & 0x80:
        position += 3 * (2 ** ((packed & 0x07) + 1))
    frames = 0
    while position < len(data):
        marker = data[position]
        position += 1
        if marker == 0x3B:
            return frames
        if marker == 0x21:
            if position >= len(data):
                break
            position += 1
            position = _skip_sub_blocks(data, position)
            continue
        if marker == 0x2C:
            if position + 9 > len(data):
                break
            image_packed = data[position + 8]
            position += 9
            if image_packed & 0x80:
                position += 3 * (2 ** ((image_packed & 0x07) + 1))
            if position >= len(data):
                break
            position += 1
            position = _skip_sub_blocks(data, position)
            frames += 1
            continue
        raise ValueError("cấu trúc GIF không hợp lệ")
    raise ValueError("GIF bị thiếu trailer hoặc dữ liệu frame")


def _skip_sub_blocks(data: bytes, position: int) -> int:
    while position < len(data):
        length = data[position]
        position += 1
        if length == 0:
            return position
        position += length
        if position > len(data):
            break
    raise ValueError("GIF có data block bị cắt")


def _to_candidate(item: AnimatedTemplate, output: Path, project_root: Path) -> MemeCandidate:
    tags: set[str] = set(tokenize(item.name))
    emotions: set[str] = set()
    styles: set[str] = {"animated", "reaction-gif", "gif động"}
    intensities = []
    for label in item.labels:
        semantic = SEMANTICS[label]
        tags.update(semantic["tags"])
        emotions.update(semantic["emotion"])
        styles.update(semantic["style"])
        intensities.append(semantic["intensity"])
    tags.update(item.aliases)
    parsed = urlparse(str(item.url))
    parts = parsed.path.lstrip("/").split("/")
    owner, repository, revision = parts[:3]
    source_path = "/".join(parts[3:])
    if owner == "cheesits456":
        license_note = (
            "Kho GitHub khai báo AGPL-3.0 cho project; quyền đối với hình ảnh/nhân vật gốc có "
            "thể thuộc chủ sở hữu khác. Hãy tự xác minh trước khi xuất bản thương mại."
        )
    else:
        license_note = (
            "README của kho nguồn nói bản quyền hình ảnh thuộc các chủ sở hữu tương ứng; "
            "không có giấy phép media riêng. Hãy tự xác minh trước khi xuất bản thương mại."
        )
    return MemeCandidate(
        id=f"popular-gif-{item.gif_id}",
        filename=output.resolve().relative_to(project_root).as_posix(),
        type="gif",
        tags=sorted(tags),
        emotion=sorted(emotions),
        style=sorted(styles),
        description=item.description,
        intensity=max(intensities),
        quality=item.quality,
        safe=item.safe,
        language="none",
        source="local",
        source_url=(
            f"https://github.com/{owner}/{repository}/blob/{revision}/{source_path}"
        ),
        license_note=license_note,
    )
