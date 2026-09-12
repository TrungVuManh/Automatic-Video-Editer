"""Schema pydantic cho kết quả phân tích của LLM (SPEC §24)."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..utils.files import read_json, write_json


class AnalysisError(ValueError):
    """File analysis.json sai định dạng."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MemeTiming(_StrictModel):
    """Gợi ý timing của LLM; code sẽ thay anchor/delay bằng giá trị tin cậy."""

    anchor: float = Field(ge=0)
    delay: float = Field(default=0.1, ge=0, le=2.0)
    duration: float = Field(ge=0.5, le=5.0)


class MemeOpportunity(_StrictModel):
    segment_id: int = Field(ge=0)
    insert_meme: bool
    confidence: float = Field(ge=0, le=1)
    trigger: str
    reason: str
    emotion: str
    reaction_type: str
    search_query: str
    preferred_style: str
    timing: MemeTiming
    insert_sfx: bool = False
    sfx_query: str = ""

    @model_validator(mode="after")
    def _co_du_thong_tin_khi_de_xuat(self) -> MemeOpportunity:
        if self.insert_meme:
            required = ("trigger", "reason", "emotion", "reaction_type", "search_query")
            missing = [name for name in required if not getattr(self, name).strip()]
            if missing:
                raise ValueError("đề xuất chèn meme còn trống: " + ", ".join(missing))
        if self.insert_sfx and not self.sfx_query.strip():
            raise ValueError("đề xuất chèn SFX còn trống: sfx_query")
        return self


class Analysis(_StrictModel):
    version: int = Field(default=1, ge=1)
    video: str
    backend: str
    model: str
    opportunities: list[MemeOpportunity]


def load_analysis(path: Path) -> Analysis:
    try:
        return Analysis.model_validate(read_json(path))
    except FileNotFoundError:
        raise
    except (OSError, ValueError, ValidationError) as e:
        raise AnalysisError(f"Analysis sai định dạng ({path}): {e}") from None


def save_analysis(path: Path, analysis: Analysis) -> None:
    write_json(path, analysis.model_dump(mode="json", exclude_none=True))


def format_analysis_summary(analysis: Analysis, path: Path, limit: int = 5) -> str:
    lines = [
        f"Analysis: {len(analysis.opportunities)} cơ hội dựng "
        f"({analysis.backend}/{analysis.model})"
    ]
    for item in analysis.opportunities[:limit]:
        start = item.timing.anchor + item.timing.delay
        kinds = "+".join(
            name for name, enabled in (("meme", item.insert_meme), ("SFX", item.insert_sfx))
            if enabled
        )
        query = item.search_query if item.insert_meme else item.sfx_query
        lines.append(
            f"  [{start:06.2f}s] đoạn {item.segment_id} [{kinds}]: {query} "
            f"({item.confidence:.0%})"
        )
    if len(analysis.opportunities) > limit:
        lines.append(f"  … còn {len(analysis.opportunities) - limit} cơ hội nữa")
    lines.append(f"→ {path}")
    return "\n".join(lines)
