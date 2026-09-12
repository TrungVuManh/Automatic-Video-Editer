"""Xếp hạng ứng viên bằng hàm thuần (SPEC §30–31)."""
from __future__ import annotations

from dataclasses import dataclass

from ..analyzer.schema import MemeOpportunity
from ..config import RankingSettings
from .local import tokenize
from .schema import MemeCandidate


@dataclass(frozen=True)
class RankedMeme:
    candidate: MemeCandidate
    score: float
    semantic_score: float
    emotion_score: float
    style_score: float
    quality_score: float
    novelty_score: float


def rank_memes(opportunity: MemeOpportunity, candidates: list[MemeCandidate],
               settings: RankingSettings, *, recent_ids: set[str] | None = None
               ) -> list[RankedMeme]:
    recent_ids = recent_ids or set()
    ranked = []
    for candidate in candidates:
        if not candidate.safe:
            continue
        emotion = _overlap_score(
            opportunity.emotion,
            [*candidate.emotion, *candidate.tags, candidate.description],
        )
        style = _overlap_score(
            opportunity.preferred_style,
            [*candidate.style, *candidate.tags, candidate.description],
        )
        novelty = 1 / (1 + candidate.usage_count)
        score = (
            candidate.semantic_score * settings.semantic_weight
            + emotion * settings.emotion_weight
            + style * settings.style_weight
            + candidate.quality * settings.quality_weight
            + novelty * settings.novelty_weight
        )
        if candidate.id in recent_ids:
            score -= settings.duplicate_penalty
        ranked.append(RankedMeme(
            candidate=candidate,
            score=round(score, 6),
            semantic_score=candidate.semantic_score,
            emotion_score=emotion,
            style_score=style,
            quality_score=candidate.quality,
            novelty_score=novelty,
        ))
    return sorted(ranked, key=lambda item: (-item.score, item.candidate.id))


def _overlap_score(wanted: str, values: list[str]) -> float:
    wanted_tokens = tokenize(wanted)
    if not wanted_tokens:
        return 0
    available = tokenize(" ".join(values))
    return len(wanted_tokens & available) / len(wanted_tokens)
