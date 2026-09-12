"""Tìm asset cho analysis và dựng timeline có thể duyệt/sửa."""
from __future__ import annotations

from pathlib import Path

from ..analyzer.schema import Analysis, MemeOpportunity
from ..config import RankingSettings
from ..memes.base import MemeProvider, MemeProviderError
from ..memes.ranker import rank_memes
from ..utils.logger import log
from .schema import MemeEvent, Timeline


def build_timeline(
    analysis: Analysis,
    provider: MemeProvider,
    ranking_settings: RankingSettings,
    *,
    top_k: int,
    project_root: Path,
    video_duration: float | None = None,
) -> Timeline:
    """Analysis → tìm/rank/lấy asset → Timeline. Một meme lỗi chỉ bị bỏ riêng."""
    events: list[MemeEvent] = []
    history: list[tuple[str, float]] = []
    opportunities = sorted(analysis.opportunities, key=_opportunity_start)
    for opportunity in opportunities:
        start = _opportunity_start(opportunity)
        recent_ids = {
            meme_id for meme_id, used_at in history
            if start - used_at <= ranking_settings.recent_window
        }
        try:
            candidates = provider.search(opportunity.search_query, top_k)
        except MemeProviderError as e:
            log.warning("Bỏ cơ hội đoạn %d: %s", opportunity.segment_id, e)
            continue
        ranked = rank_memes(
            opportunity,
            candidates,
            ranking_settings,
            recent_ids=recent_ids,
        )
        selected = None
        asset = None
        for item in ranked:
            try:
                asset = provider.materialize(item.candidate)
                selected = item.candidate
                break
            except MemeProviderError as e:
                log.warning("Không dùng được ứng viên %s: %s", item.candidate.id, e)
        if selected is None or asset is None:
            log.warning("Không có asset hợp lệ cho cơ hội đoạn %d (%s).",
                        opportunity.segment_id, opportunity.search_query)
            continue

        duration = opportunity.timing.duration
        if video_duration is not None:
            duration = min(duration, video_duration - start)
        if duration <= 0:
            continue
        events.append(MemeEvent(
            id=f"event_{len(events) + 1:03d}",
            start=round(start, 3),
            duration=round(duration, 3),
            asset=_portable_path(asset, project_root),
            confidence=opportunity.confidence,
            query=opportunity.search_query,
            reason=opportunity.reason,
        ))
        history.append((selected.id, start))
    return Timeline(video=analysis.video, events=events)


def _opportunity_start(opportunity: MemeOpportunity) -> float:
    return opportunity.timing.anchor + opportunity.timing.delay


def _portable_path(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())
