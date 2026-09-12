"""Thư viện meme local: JSONL có metadata + tự phát hiện file chưa mô tả."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from pydantic import ValidationError

from ..utils.logger import log
from .base import MemeProvider, MemeProviderError
from .schema import MemeCandidate

SUPPORTED = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm", ".mov"}


def parse_library(text: str) -> tuple[list[MemeCandidate], list[str]]:
    """Đọc JSONL; một dòng lỗi chỉ bị bỏ riêng và có cảnh báo chỉ đúng số dòng."""
    candidates: list[MemeCandidate] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for line_no, raw in enumerate(text.splitlines(), 1):
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        try:
            item = MemeCandidate.model_validate(json.loads(raw))
            if item.id in seen:
                raise ValueError(f"trùng id {item.id!r}")
            seen.add(item.id)
            candidates.append(item)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            warnings.append(f"library.jsonl dòng {line_no}: {e}")
    return candidates, warnings


def tokenize(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    return set(re.findall(r"[a-z0-9]+", normalized))


def local_semantic_score(query: str, candidate: MemeCandidate) -> float:
    """Fallback lexical nhẹ; semantic search thật do Meme Search đảm nhiệm."""
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0
    metadata = " ".join([
        candidate.id,
        candidate.filename,
        candidate.description,
        *candidate.tags,
        *candidate.emotion,
        *candidate.style,
    ])
    matched = query_tokens & tokenize(metadata)
    phrase_bonus = 0.15 if query.casefold() in metadata.casefold() else 0
    return min(1.0, len(matched) / len(query_tokens) + phrase_bonus)


class LocalMemeProvider(MemeProvider):
    def __init__(self, *, library_file: Path, asset_dirs: list[Path], project_root: Path):
        self.library_file = Path(library_file)
        self.asset_dirs = [Path(path) for path in asset_dirs]
        self.project_root = Path(project_root)
        self._items: list[MemeCandidate] | None = None

    def search(self, query: str, limit: int = 10) -> list[MemeCandidate]:
        scored = []
        for item in self._load():
            if not item.safe:
                continue
            score = local_semantic_score(query, item)
            if score > 0:
                scored.append(item.model_copy(update={"semantic_score": score}))
        return sorted(scored, key=lambda x: (-x.semantic_score, x.id))[:limit]

    def materialize(self, candidate: MemeCandidate) -> Path:
        path = Path(candidate.filename).expanduser()
        attempts = [path] if path.is_absolute() else [
            self.project_root / path,
            self.library_file.parent / path,
            *(directory / path for directory in self.asset_dirs),
        ]
        for attempt in attempts:
            resolved = attempt.resolve()
            if resolved.is_file():
                return resolved
        raise MemeProviderError(
            f"Không thấy file local của meme {candidate.id}: {candidate.filename}"
        )

    def _load(self) -> list[MemeCandidate]:
        if self._items is not None:
            return self._items
        items: list[MemeCandidate] = []
        if self.library_file.exists():
            items, warnings = parse_library(self.library_file.read_text(encoding="utf-8"))
            for warning in warnings:
                log.warning("%s", warning)

        known = {self._normalized_path(item.filename) for item in items}
        ids = {item.id for item in items}
        for directory in self.asset_dirs:
            if not directory.exists():
                continue
            for path in sorted(directory.rglob("*")):
                supported = path.suffix.casefold() in SUPPORTED
                if path.is_symlink() or not path.is_file() or not supported:
                    continue
                relative = self._relative_filename(path)
                if self._normalized_path(relative) in known:
                    continue
                candidate_id = _unique_id(path.stem, ids)
                ids.add(candidate_id)
                items.append(MemeCandidate(
                    id=candidate_id,
                    filename=relative,
                    type=media_type(path),
                    tags=sorted(tokenize(path.stem)),
                ))
        self._items = items
        return items

    def _relative_filename(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.project_root.resolve()).as_posix()
        except ValueError:
            return str(path.resolve())

    @staticmethod
    def _normalized_path(filename: str) -> str:
        return str(Path(filename)).replace("\\", "/").casefold()


def media_type(path: Path) -> str:
    suffix = path.suffix.casefold()
    if suffix == ".gif":
        return "gif"
    if suffix in {".mp4", ".webm", ".mov"}:
        return "video"
    return "image"


def _unique_id(stem: str, existing: set[str]) -> str:
    base = "-".join(sorted(tokenize(stem))) or "meme"
    candidate = base
    number = 2
    while candidate in existing:
        candidate = f"{base}-{number}"
        number += 1
    return candidate
