"""Tạo provider theo cấu hình, luôn giữ local làm fallback."""
from __future__ import annotations

from typing import Any

from .base import MemeProvider
from .local import LocalMemeProvider
from .meme_search import FallbackMemeProvider, MemeSearchProvider


def create_meme_provider(settings: Any) -> MemeProvider:
    assets = settings.paths.assets_dir
    root = assets.parent
    local = LocalMemeProvider(
        library_file=settings.meme.library_file,
        asset_dirs=[assets / "memes", assets / "gifs"],
        project_root=root,
    )
    if not settings.meme_search.token:
        return local
    remote = MemeSearchProvider(
        base_url=settings.meme_search.base_url,
        token=settings.meme_search.token,
        cache_dir=settings.paths.data_dir / "cache" / "meme-search",
        max_download_mb=settings.meme_search.max_download_mb,
    )
    return FallbackMemeProvider(remote, local)
