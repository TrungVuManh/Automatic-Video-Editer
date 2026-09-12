"""Tìm asset cho analysis và dựng timeline có thể duyệt/sửa."""
from __future__ import annotations

from pathlib import Path

from ..analyzer.schema import Analysis, MemeOpportunity
from ..config import RankingSettings, SfxSettings
from ..memes.base import MemeProvider, MemeProviderError
from ..memes.ranker import rank_memes
from ..sfx.library import LocalSfxProvider
from ..utils.logger import log
from .schema import MemeEvent, SfxEvent, Timeline, TimelineEvent


def build_timeline(
    analysis: Analysis,
    provider: MemeProvider,
    ranking_settings: RankingSettings,
    *,
    top_k: int,
    project_root: Path,
    video_duration: float | None = None,
    sfx_provider: LocalSfxProvider | None = None,
    sfx_settings: SfxSettings | None = None,
) -> Timeline:
    """Analysis → tìm/rank/lấy meme và SFX → Timeline có thể duyệt."""
    events: list[TimelineEvent] = []
    history: list[tuple[str, float]] = []
    sfx_history: list[float] = []
    opportunities = sorted(analysis.opportunities, key=_opportunity_start)
    for opportunity in opportunities:
        start = _opportunity_start(opportunity)
        if opportunity.insert_meme:
            recent_ids = {
                meme_id for meme_id, used_at in history
                if start - used_at <= ranking_settings.recent_window
            }
            try:
                candidates = provider.search(opportunity.search_query, top_k)
            except MemeProviderError as e:
                log.warning("Bỏ meme ở đoạn %d: %s", opportunity.segment_id, e)
                candidates = []
            ranked = rank_memes(
                opportunity, candidates, ranking_settings, recent_ids=recent_ids,
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
            if selected is not None and asset is not None:
                duration = _clamped_duration(opportunity.timing.duration, start, video_duration)
                if duration > 0:
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
            else:
                log.warning("Không có meme hợp lệ cho đoạn %d (%s).",
                            opportunity.segment_id, opportunity.search_query)

        if (
            opportunity.insert_sfx
            and sfx_provider is not None
            and sfx_settings is not None
            and sfx_settings.enabled
            and _sfx_density_allows(start, sfx_history, video_duration, sfx_settings)
        ):
            matches = sfx_provider.search(opportunity.sfx_query, top_k)
            selected_sfx = next(
                (item for item in matches if item.semantic_score >= sfx_settings.score_threshold),
                None,
            )
            if selected_sfx is None:
                log.warning("Không có SFX đủ khớp cho đoạn %d (%s).",
                            opportunity.segment_id, opportunity.sfx_query)
                continue
            try:
                sfx_asset = sfx_provider.materialize(selected_sfx)
            except FileNotFoundError as exc:
                log.warning("Không dùng được SFX %s: %s", selected_sfx.id, exc)
                continue
            duration = _clamped_duration(
                min(selected_sfx.duration, sfx_settings.duration_max), start, video_duration,
            )
            if duration > 0:
                events.append(SfxEvent(
                    id=f"event_{len(events) + 1:03d}",
                    start=round(start, 3),
                    duration=round(duration, 3),
                    asset=_portable_path(sfx_asset, project_root),
                    volume=round(sfx_settings.volume * selected_sfx.recommended_volume, 3),
                    confidence=opportunity.confidence,
                    query=opportunity.sfx_query,
                    reason=opportunity.reason,
                ))
                sfx_history.append(start)
    return Timeline(video=analysis.video, events=events)


def _clamped_duration(duration: float, start: float, video_duration: float | None) -> float:
    if video_duration is not None:
        duration = min(duration, video_duration - start)
    return max(0.0, duration)


def _sfx_density_allows(
    start: float, history: list[float], video_duration: float | None, settings: SfxSettings,
) -> bool:
    if history and start - history[-1] < settings.cooldown:
        return False
    if video_duration and video_duration > 0:
        maximum = max(1, int(video_duration * settings.max_per_minute / 60))
        return len(history) < maximum
    return True


def _opportunity_start(opportunity: MemeOpportunity) -> float:
    return opportunity.timing.anchor + opportunity.timing.delay


def _portable_path(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())
