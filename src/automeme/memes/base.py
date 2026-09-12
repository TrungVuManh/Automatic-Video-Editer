"""Interface nguồn meme, tách pipeline khỏi local filesystem và API ngoài."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from .schema import MemeCandidate


class MemeProviderError(RuntimeError):
    """Một nguồn meme không tìm hoặc lấy được asset."""


class MemeProvider(ABC):
    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[MemeCandidate]:
        """Trả tối đa `limit` ứng viên đã có semantic_score."""

    @abstractmethod
    def materialize(self, candidate: MemeCandidate) -> Path:
        """Đảm bảo asset có trên máy và trả đường dẫn local."""
