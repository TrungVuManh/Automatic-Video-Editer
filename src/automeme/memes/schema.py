"""Metadata chung cho ứng viên từ local và Meme Search (SPEC §26)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MemeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    type: Literal["image", "gif", "video"]
    tags: list[str] = Field(default_factory=list)
    emotion: list[str] = Field(default_factory=list)
    style: list[str] = Field(default_factory=list)
    description: str = ""
    intensity: float = Field(default=0.5, ge=0, le=1)
    quality: float = Field(default=0.5, ge=0, le=1)
    safe: bool = True
    language: str = "none"
    usage_count: int = Field(default=0, ge=0)
    semantic_score: float = Field(default=0, ge=0, le=1)
    source: Literal["local", "meme-search"] = "local"
    content_url: str | None = None
