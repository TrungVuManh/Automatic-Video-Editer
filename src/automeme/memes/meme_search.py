"""Adapter cho Meme Search API v1 và fallback local."""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from ..utils.logger import log
from .base import MemeProvider, MemeProviderError
from .schema import MemeCandidate


class MemeSearchProvider(MemeProvider):
    def __init__(self, *, base_url: str, token: str, cache_dir: Path,
                 max_download_mb: float = 25,
                 client_factory: Callable[..., Any] | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.cache_dir = Path(cache_dir)
        self.max_download_bytes = int(max_download_mb * 1024 * 1024)
        self._client_factory = client_factory

    def search(self, query: str, limit: int = 10) -> list[MemeCandidate]:
        if not self.token:
            raise MemeProviderError("Meme Search chưa có token.")
        limit = min(20, max(1, limit))
        client = self._client()
        try:
            response = client.get(
                "/api/v1/search",
                params={"q": query[:200], "mode": "vector", "limit": limit},
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("data")
            if not isinstance(rows, list):
                raise MemeProviderError("Meme Search trả JSON thiếu mảng `data`.")
            candidates = []
            count = max(1, len(rows))
            for index, row in enumerate(rows[:limit]):
                if not isinstance(row, dict):
                    continue
                try:
                    candidates.append(_candidate_from_api(
                        row,
                        semantic_score=max(0.1, 1 - index / count),
                    ))
                except (KeyError, TypeError, ValueError) as e:
                    log.warning("Bỏ kết quả Meme Search #%d vì sai schema: %s", index, e)
            return candidates
        except MemeProviderError:
            raise
        except Exception as e:
            raise MemeProviderError(f"Không tìm được qua Meme Search {self.base_url}: {e}") from e
        finally:
            _close(client)

    def materialize(self, candidate: MemeCandidate) -> Path:
        if not candidate.content_url:
            raise MemeProviderError(f"Meme Search thiếu content_url cho {candidate.id}.")
        url = self._safe_content_url(candidate.content_url)
        filename = _safe_filename(candidate.filename)
        output = self.cache_dir / f"{_safe_filename(candidate.id)}-{filename}"
        if output.is_file():
            return output

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = output.with_name(output.name + ".part")
        client = self._client()
        try:
            with client.stream("GET", url) as response:
                if 300 <= response.status_code < 400:
                    raise MemeProviderError(
                        "Meme Search trả redirect; từ chối gửi token sang URL khác."
                    )
                response.raise_for_status()
                declared = response.headers.get("content-length")
                if declared and int(declared) > self.max_download_bytes:
                    raise MemeProviderError(
                        f"Meme {candidate.id} lớn hơn giới hạn "
                        f"{self.max_download_bytes / 1024 / 1024:g} MB."
                    )
                size = 0
                with open(tmp, "wb") as file:
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > self.max_download_bytes:
                            raise MemeProviderError(
                                f"Meme {candidate.id} vượt giới hạn khi đang tải."
                            )
                        file.write(chunk)
            tmp.replace(output)
            return output
        except MemeProviderError:
            _unlink(tmp)
            raise
        except Exception as e:
            _unlink(tmp)
            raise MemeProviderError(f"Không tải được meme {candidate.id}: {e}") from e
        finally:
            _close(client)

    def _client(self):
        headers = {"Authorization": f"Bearer {self.token}"}
        if self._client_factory is not None:
            return self._client_factory(
                base_url=self.base_url,
                headers=headers,
                timeout=15,
                follow_redirects=False,
            )
        import httpx

        return httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=15,
            follow_redirects=False,
        )

    def _safe_content_url(self, content_url: str) -> str:
        base = urlparse(self.base_url)
        target = urlparse(urljoin(self.base_url + "/", content_url))
        if target.scheme not in {"http", "https"} or (
            target.scheme.casefold(), target.netloc.casefold()
        ) != (base.scheme.casefold(), base.netloc.casefold()):
            raise MemeProviderError("content_url của Meme Search trỏ sang origin khác.")
        return target.geturl()


class FallbackMemeProvider(MemeProvider):
    """Ghép kết quả API và local; API chết thì local vẫn hoạt động."""

    def __init__(self, primary: MemeProvider, fallback: MemeProvider):
        self.primary = primary
        self.fallback = fallback

    def search(self, query: str, limit: int = 10) -> list[MemeCandidate]:
        primary: list[MemeCandidate] = []
        try:
            primary = self.primary.search(query, limit)
        except MemeProviderError as e:
            log.warning("%s Dùng thư viện meme local.", e)
        local = self.fallback.search(query, limit)
        merged: list[MemeCandidate] = []
        seen: set[tuple[str, str]] = set()
        for item in [*primary, *local]:
            key = (item.source, item.id)
            if key not in seen:
                seen.add(key)
                merged.append(item)
        return merged[:limit]

    def materialize(self, candidate: MemeCandidate) -> Path:
        provider = self.primary if candidate.source == "meme-search" else self.fallback
        return provider.materialize(candidate)


def _candidate_from_api(row: dict[str, Any], *, semantic_score: float) -> MemeCandidate:
    media_type = str(row["media_type"]).casefold()
    if media_type == "image/gif":
        kind = "gif"
    elif media_type.startswith("video/"):
        kind = "video"
    elif media_type.startswith("image/"):
        kind = "image"
    else:
        raise ValueError(f"media_type không hỗ trợ: {media_type}")
    return MemeCandidate(
        id=f"meme-search-{row['id']}",
        filename=str(row["filename"]),
        type=kind,
        tags=[str(tag) for tag in row.get("tags") or []],
        description=str(row.get("description") or ""),
        quality=0.7,
        semantic_score=semantic_score,
        source="meme-search",
        content_url=str(row["content_url"]),
    )


def _safe_filename(value: str) -> str:
    name = Path(value).name
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")
    return safe[:100] or "meme"


def _close(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        close()


def _unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
