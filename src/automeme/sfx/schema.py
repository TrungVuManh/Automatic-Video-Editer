"""Schema metadata riêng cho sound effect."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SfxCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    type: Literal["audio"] = "audio"
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
    source: Literal["local"] = "local"
    source_url: str | None = None
    license_note: str | None = None
    duration: float = Field(gt=0, le=10)
    recommended_volume: float = Field(default=0.7, ge=0, le=1)
