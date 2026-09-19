"""Gọi LLM, kiểm tra output và áp ràng buộc cứng bằng code."""
from __future__ import annotations

import math
from dataclasses import dataclass

from pydantic import ValidationError

from ..utils.logger import log
from .base import LLMRefusal, StructuredLLM
from .context import ContextWindow
from .prompt import render_prompt
from .schema import MemeOpportunity, MemeTiming


@dataclass(frozen=True)
class FilterSettings:
    threshold: float
    cooldown: float
    max_per_minute: float
    duration_min: float
    duration_max: float
    timing_delay: float


def detect_opportunities(contexts: list[ContextWindow], llm: StructuredLLM,
                         prompt_template: str) -> list[MemeOpportunity]:
    """Phân tích từng cửa sổ; JSON sai thử lại một lần rồi bỏ riêng ứng viên đó."""
    schema = MemeOpportunity.model_json_schema()
    opportunities: list[MemeOpportunity] = []
    for index, context in enumerate(contexts, 1):
        prompt = render_prompt(prompt_template, context, schema)
        candidate = None
        tu_choi = False
        for attempt in range(2):
            attempt_prompt = prompt
            if attempt:
                attempt_prompt += (
                    "\n\nLần trả lời trước không hợp lệ. Hãy sửa và chỉ trả đúng một JSON object "
                    "khớp hoàn toàn schema."
                )
            try:
                raw = llm.complete(attempt_prompt, schema)
            except LLMRefusal as e:
                log.warning("Bỏ đoạn %s: %s", context.segment_id, e)
                tu_choi = True
                break
            try:
                candidate = MemeOpportunity.model_validate_json(raw)
                if candidate.segment_id != context.segment_id:
                    raise ValueError(
                        f"segment_id {candidate.segment_id} không khớp {context.segment_id}"
                    )
                break
            except (ValidationError, ValueError) as e:
                candidate = None
                level = log.warning if attempt else log.debug
                level("LLM trả JSON sai cho đoạn %s (lần %d/2): %s",
                      context.segment_id, attempt + 1, e)
        if candidate is None:
            if not tu_choi:
                log.warning("Bỏ đoạn %s vì LLM trả JSON sai hai lần.", context.segment_id)
            continue
        opportunities.append(candidate)
        log.info("Phân tích LLM: %d/%d đoạn", index, len(contexts))
    return opportunities


def filter_opportunities(
    opportunities: list[MemeOpportunity],
    contexts: list[ContextWindow],
    settings: FilterSettings,
    *,
    video_duration: float,
) -> list[MemeOpportunity]:
    """Code quyết định confidence, timing, duration, cooldown và mật độ (SPEC §51–53)."""
    by_id = {context.segment_id: context for context in contexts}
    normalized: list[MemeOpportunity] = []
    for item in opportunities:
        context = by_id.get(item.segment_id)
        if (
            not (item.insert_meme or item.insert_sfx)
            or item.confidence < settings.threshold
            or context is None
        ):
            continue
        start = context.end + settings.timing_delay
        remaining = video_duration - start
        if remaining < settings.duration_min:
            continue
        # Làm tròn tới mili giây: cộng trừ float để lại đuôi kiểu 1.129999999999999
        timing = MemeTiming(
            anchor=round(context.end, 3),
            delay=round(settings.timing_delay, 3),
            duration=round(min(
                settings.duration_max,
                remaining,
                max(settings.duration_min, item.timing.duration),
            ), 3),
        )
        normalized.append(item.model_copy(update={"timing": timing}))

    # Ưu tiên cơ hội tự tin nhất; cooldown được kiểm tra hai phía với các cơ hội đã giữ.
    chosen: list[MemeOpportunity] = []
    for item in sorted(normalized, key=lambda x: x.confidence, reverse=True):
        start = _start(item)
        if all(abs(start - _start(other)) >= settings.cooldown for other in chosen):
            chosen.append(item)

    maximum = max(1, math.floor(video_duration * settings.max_per_minute / 60))
    chosen = sorted(chosen, key=lambda x: x.confidence, reverse=True)[:maximum]
    return sorted(chosen, key=_start)


def _start(item: MemeOpportunity) -> float:
    return item.timing.anchor + item.timing.delay
