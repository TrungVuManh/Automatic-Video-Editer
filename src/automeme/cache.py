"""Manifest nội bộ để resume đúng và vô hiệu cache theo đầu vào từng bước."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from .utils.files import read_json, write_json

CacheStatus = Literal["missing", "fresh", "stale", "modified", "untracked"]


class ArtifactManifest(BaseModel):
    """Dấu vết của một artifact do automeme tạo; không chứa token hay nội dung media."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    stage: Literal["analysis", "timeline", "render"]
    artifact: str
    input_key: str
    output_fingerprint: str


def stable_key(value: Any, *, length: int = 16) -> str:
    """Băm JSON ổn định; dict khác thứ tự vẫn cho cùng khóa."""
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:length]


def file_fingerprint(path: Path, *, block_size: int = 1024 * 1024,
                     length: int = 16) -> str:
    """Vân tay nhanh của file: kích thước + phần đầu/cuối, phù hợp cả video lớn."""
    path = Path(path)
    size = path.stat().st_size
    digest = hashlib.sha256()
    digest.update(str(size).encode("ascii"))
    with open(path, "rb") as file:
        digest.update(file.read(block_size))
        if size > block_size:
            file.seek(max(0, size - block_size))
            digest.update(file.read(block_size))
    return digest.hexdigest()[:length]


def manifest_path(data_dir: Path, artifact: Path, stage: str) -> Path:
    """Đường dẫn manifest trung tâm; không tạo sidecar cạnh file output của người dùng."""
    identity = stable_key(str(Path(artifact).resolve()), length=20)
    return Path(data_dir) / "cache" / "manifests" / f"{stage}-{identity}.json"


def artifact_status(artifact: Path, manifest_file: Path, *, stage: str,
                    input_key: str) -> CacheStatus:
    """Phân biệt cache cũ, stale và file đã được người dùng sửa."""
    artifact = Path(artifact)
    if not artifact.is_file():
        return "missing"
    try:
        manifest = ArtifactManifest.model_validate(read_json(manifest_file))
    except (FileNotFoundError, OSError, ValueError, ValidationError):
        return "untracked"
    if manifest.stage != stage or Path(manifest.artifact).resolve() != artifact.resolve():
        return "untracked"
    if manifest.output_fingerprint != file_fingerprint(artifact):
        return "modified"
    if manifest.input_key != input_key:
        return "stale"
    return "fresh"


def record_artifact(artifact: Path, manifest_file: Path, *, stage: str,
                    input_key: str) -> None:
    """Ghi manifest sau khi artifact đã hoàn tất; `write_json` dùng file tạm + replace."""
    artifact = Path(artifact)
    manifest = ArtifactManifest(
        stage=stage,
        artifact=str(artifact.resolve()),
        input_key=input_key,
        output_fingerprint=file_fingerprint(artifact),
    )
    write_json(manifest_file, manifest.model_dump(mode="json"))
