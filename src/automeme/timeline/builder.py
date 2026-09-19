"""Tìm asset cho analysis và dựng timeline có thể duyệt/sửa.

LLM chỉ đề xuất khoảnh khắc; **code** quyết định cách dựng (SPEC §53), theo `configs/`:

- Khoảnh khắc nào được **cắt tràn màn hình** (`cutaway.mode: auto`): tự tin nhất, cách nhau đủ
  xa, không quá `cutaway.max_per_minute`; ưu tiên GIF vì chuyển động đọc được ngay.
- Mỗi cú cắt có **zoom** vào gameplay ngay trước đó và một **SFX** đúng lúc cắt.
- SFX không lặp lại cùng một file trong `ranking.recent_window` giây.
- Template cần chữ (`meme.exclude_styles`) không được tự chọn; meme ở góc luân phiên theo
  `meme.position_cycle` để tránh che facecam.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

from ..analyzer.schema import Analysis, MemeOpportunity
from ..config import CutawaySettings, MemeSettings, RankingSettings, SfxSettings
from ..memes.base import MemeProvider, MemeProviderError
from ..memes.ranker import RankedMeme, rank_memes
from ..sfx.library import LocalSfxProvider
from ..utils.logger import log
from .schema import MemeEvent, SfxEvent, Timeline, TimelineEvent, ZoomEvent

ZOOM_LAN_SANG_CUT = 0.1   # zoom kéo dài qua lúc cắt một chút để pha thu zoom nằm dưới meme
CHENH_DIEM_UU_TIEN_GIF = 0.1  # GIF kém ứng viên tốt nhất không quá chừng này điểm thì được ưu tiên


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
    cutaway_settings: CutawaySettings | None = None,
    meme_settings: MemeSettings | None = None,
) -> Timeline:
    """Analysis → tìm/rank/lấy meme và SFX → Timeline có thể duyệt."""
    events: list[TimelineEvent] = []
    history: list[tuple[str, float]] = []
    sfx_history: list[float] = []
    sfx_used: list[tuple[str, float]] = []
    opportunities = sorted(analysis.opportunities, key=_opportunity_start)
    cutaways = pick_cutaways(opportunities, cutaway_settings, video_duration)
    exclude = set(meme_settings.exclude_styles) if meme_settings else set()
    cycle = list(meme_settings.position_cycle) if meme_settings else []
    so_meme_goc = 0

    def next_id() -> str:
        return f"event_{len(events) + 1:03d}"

    for index, opportunity in enumerate(opportunities):
        start = _opportunity_start(opportunity)
        cut = index in cutaways
        meme_added = False
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
            candidates = [c for c in candidates if not exclude & set(c.style)]
            ranked = rank_memes(
                opportunity, candidates, ranking_settings, recent_ids=recent_ids,
            )
            if cut:
                ranked = prefer_animated(ranked)
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
                duration = opportunity.timing.duration
                if cut:
                    duration = min(max(duration, cutaway_settings.duration_min),
                                   cutaway_settings.duration_max)
                duration = _clamped_duration(duration, start, video_duration)
                if duration > 0:
                    if cut and cutaway_settings.punch_zoom:
                        zoom = punch_zoom(start, cutaway_settings, next_id())
                        if zoom is not None:
                            events.append(zoom)
                    position = None
                    if not cut and cycle:
                        position = cycle[so_meme_goc % len(cycle)]
                        so_meme_goc += 1
                    events.append(MemeEvent(
                        id=next_id(),
                        start=round(start, 3),
                        duration=round(duration, 3),
                        asset=_portable_path(asset, project_root),
                        mode="cutaway" if cut else "overlay",
                        position=position,
                        confidence=opportunity.confidence,
                        query=opportunity.search_query,
                        reason=opportunity.reason,
                    ))
                    history.append((selected.id, start))
                    meme_added = True
            else:
                log.warning("Không có meme hợp lệ cho đoạn %d (%s).",
                            opportunity.segment_id, opportunity.search_query)

        # Cú cắt tràn màn hình luôn có SFX đi kèm (không tính vào giới hạn mật độ SFX thường,
        # vì số cú cắt đã được giới hạn riêng); SFX AI đề xuất thì theo giới hạn mật độ.
        cut_sfx = cut and meme_added and cutaway_settings.sfx_on_cut
        if (
            (opportunity.insert_sfx or cut_sfx)
            and sfx_provider is not None
            and sfx_settings is not None
            and sfx_settings.enabled
            and (cut_sfx or _sfx_density_allows(start, sfx_history, video_duration, sfx_settings))
        ):
            # Cú cắt: truy vấn của AI không còn file nào chưa dùng gần đây thì thử truy vấn mặc
            # định — cú cắt thiếu âm nghe hụt hẫng (lỗi thật khi nghiệm thu livestream).
            queries = [q for q in dict.fromkeys([
                opportunity.sfx_query.strip(),
                cutaway_settings.sfx_query.strip() if cut_sfx else "",
            ]) if q]
            if not queries:
                continue
            recent_sfx = {
                sfx_id for sfx_id, used_at in sfx_used
                if start - used_at <= ranking_settings.recent_window
            }
            selected_sfx = None
            for query in queries:
                selected_sfx = next(
                    (item for item in sfx_provider.search(query, top_k)
                     if item.semantic_score >= sfx_settings.score_threshold
                     and item.id not in recent_sfx),
                    None,
                )
                if selected_sfx is not None:
                    break
            if selected_sfx is None:
                log.warning("Không có SFX đủ khớp (và chưa dùng gần đây) cho đoạn %d (%s).",
                            opportunity.segment_id, " / ".join(queries))
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
                    id=next_id(),
                    start=round(start, 3),
                    duration=round(duration, 3),
                    asset=_portable_path(sfx_asset, project_root),
                    volume=round(
                        (cutaway_settings.sfx_volume if cut_sfx else sfx_settings.volume)
                        * selected_sfx.recommended_volume, 3),
                    confidence=opportunity.confidence,
                    query=query,
                    reason=opportunity.reason,
                ))
                sfx_history.append(start)
                sfx_used.append((selected_sfx.id, start))
    return Timeline(video=analysis.video, events=events)


def pick_cutaways(opportunities: Sequence[MemeOpportunity], settings: CutawaySettings | None,
                  video_duration: float | None) -> set[int]:
    """Chỉ số các cơ hội được cắt tràn màn hình: tự tin nhất trước, cách nhau ≥ cooldown
    (đầu → đầu), tối đa `max(1, floor(thời lượng × max_per_minute / 60))` và không quá
    `max_share` số meme. Cùng độ tự tin thì ưu tiên khoảnh khắc AI đề xuất cả SFX (tín hiệu
    mạnh hơn), rồi đến khoảnh khắc sớm hơn. Hàm thuần."""
    if settings is None or settings.mode != "auto":
        return set()
    ung_vien = [
        (i, o) for i, o in enumerate(opportunities)
        if o.insert_meme and o.confidence >= settings.min_confidence
    ]
    toi_da = (max(1, math.floor(video_duration * settings.max_per_minute / 60))
              if video_duration else len(ung_vien))
    so_meme = sum(1 for o in opportunities if o.insert_meme)
    toi_da = min(toi_da, max(1, math.floor(so_meme * settings.max_share)))
    chon: list[int] = []
    # sort ổn định: bằng điểm và cùng có/không SFX thì khoảnh khắc sớm hơn đứng trước
    for i, o in sorted(ung_vien, key=lambda item: (-item[1].confidence, not item[1].insert_sfx)):
        if len(chon) >= toi_da:
            break
        start = _opportunity_start(o)
        if all(abs(start - _opportunity_start(opportunities[j])) >= settings.cooldown
               for j in chon):
            chon.append(i)
    return set(chon)


def prefer_animated(ranked: list[RankedMeme]) -> list[RankedMeme]:
    """Đưa GIF/video lên đầu nếu điểm không kém ứng viên tốt nhất quá `CHENH_DIEM_UU_TIEN_GIF` —
    cú cắt tràn màn hình cần chuyển động; ảnh tĩnh phóng to dễ trông như slide."""
    if not ranked:
        return ranked
    nguong = ranked[0].score - CHENH_DIEM_UU_TIEN_GIF
    dong = [r for r in ranked if r.candidate.type in ("gif", "video") and r.score >= nguong]
    return dong + [r for r in ranked if r not in dong]


def punch_zoom(cut_start: float, settings: CutawaySettings, event_id: str) -> ZoomEvent | None:
    """Zoom vào gameplay ngay trước cú cắt, kéo qua lúc cắt một chút (pha thu zoom bị meme che)."""
    start = max(0.0, cut_start - settings.zoom_duration)
    duration = cut_start - start + ZOOM_LAN_SANG_CUT
    if cut_start - start < 0.05:
        return None  # cú cắt ở ngay đầu video: không có chỗ để zoom
    return ZoomEvent(id=event_id, start=round(start, 3), duration=round(duration, 3),
                     factor=settings.zoom_factor, reason="zoom trước cú cắt tràn màn hình")


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
