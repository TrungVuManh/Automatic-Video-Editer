import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from automeme.analyzer.base import StructuredLLM
from automeme.analyzer.context import ContextWindow, build_context_windows
from automeme.analyzer.detector import (
    FilterSettings,
    detect_opportunities,
    filter_opportunities,
)
from automeme.analyzer.llm import ClaudeLLM, OllamaLLM, create_llm
from automeme.analyzer.prompt import load_prompt, render_prompt
from automeme.analyzer.schema import Analysis, MemeOpportunity
from automeme.config import load_settings


def opportunity(segment_id=0, *, insert=True, confidence=0.9, anchor=1.0, duration=1.5):
    return MemeOpportunity.model_validate({
        "segment_id": segment_id,
        "insert_meme": insert,
        "confidence": confidence,
        "trigger": "punchline" if insert else "",
        "reason": "câu trả lời bất ngờ" if insert else "",
        "emotion": "bối rối" if insert else "",
        "reaction_type": "confused reaction" if insert else "",
        "search_query": "confused man reaction" if insert else "",
        "preferred_style": "reaction",
        "timing": {"anchor": anchor, "delay": 0.1, "duration": duration},
    })


def test_build_context_windows_dung_bien():
    transcript = {"segments": [
        {"id": 0, "start": 0, "end": 1, "text": "Ai giữ tiền?"},
        {"id": 1, "start": 1, "end": 2, "text": "Tôi."},
        {"id": 2, "start": 2, "end": 3, "text": "Vợ tôi giữ hộ."},
        {"id": 3, "start": 3, "end": 4, "text": "Thật à?"},
    ]}
    windows = build_context_windows(transcript, previous_count=2, next_count=1)
    assert windows[0].previous == ()
    assert windows[0].next == ("Tôi.",)
    assert windows[2].previous == ("Ai giữ tiền?", "Tôi.")
    assert windows[2].current == "Vợ tôi giữ hộ."
    assert windows[2].next == ("Thật à?",)


def test_context_count_am_bi_chan():
    with pytest.raises(ValueError, match="không được âm"):
        build_context_windows({"segments": []}, previous_count=-1)


def test_prompt_doc_utf8_va_co_schema(tmp_path):
    path = tmp_path / "prompt.txt"
    path.write_text("A {{CONTEXT_JSON}} B {{SCHEMA_JSON}}", encoding="utf-8")
    template = load_prompt(path)
    text = render_prompt(template, ContextWindow(2, 1, 2, ("trước",), "Vợ tôi", ()),
                         MemeOpportunity.model_json_schema())
    assert "Vợ tôi" in text and '"segment_id"' in text


def test_prompt_thieu_placeholder_bao_ro(tmp_path):
    path = tmp_path / "prompt.txt"
    path.write_text("không đủ", encoding="utf-8")
    with pytest.raises(ValueError, match="CONTEXT_JSON"):
        load_prompt(path)


def test_schema_chan_output_llm_sai():
    data = opportunity().model_dump()
    data["confidence"] = 1.2
    with pytest.raises(ValidationError):
        MemeOpportunity.model_validate(data)
    data = opportunity().model_dump()
    data["search_query"] = ""
    with pytest.raises(ValidationError, match="search_query"):
        MemeOpportunity.model_validate(data)
    with pytest.raises(ValidationError):
        Analysis.model_validate({"version": 1, "video": "v.mp4", "backend": "x",
                                 "model": "m", "opportunities": [], "thua": True})


class FakeLLM(StructuredLLM):
    model = "fake"

    def __init__(self, answers):
        self.answers = iter(answers)
        self.calls = 0

    def complete(self, prompt, schema):
        self.calls += 1
        assert "JSON SCHEMA" in prompt or "schema" in prompt.lower()
        assert schema["title"] == "MemeOpportunity"
        return next(self.answers)


def test_json_hong_thu_lai_mot_lan_roi_thanh_cong():
    context = ContextWindow(0, 0, 1, (), "Một câu", ())
    llm = FakeLLM(["không phải json", opportunity().model_dump_json()])
    found = detect_opportunities([context], llm, "{{CONTEXT_JSON}} JSON SCHEMA {{SCHEMA_JSON}}")
    assert found == [opportunity()]
    assert llm.calls == 2


def test_json_hong_hai_lan_thi_bo_riêng_ung_vien():
    contexts = [ContextWindow(0, 0, 1, (), "A", ()), ContextWindow(1, 1, 2, (), "B", ())]
    llm = FakeLLM(["x", "y", opportunity(1).model_dump_json()])
    found = detect_opportunities(contexts, llm, "{{CONTEXT_JSON}} schema {{SCHEMA_JSON}}")
    assert [item.segment_id for item in found] == [1]
    assert llm.calls == 3


def test_segment_id_sai_cung_phai_retry():
    context = ContextWindow(3, 0, 1, (), "Một câu", ())
    llm = FakeLLM([opportunity(2).model_dump_json(), opportunity(3).model_dump_json()])
    found = detect_opportunities([context], llm, "{{CONTEXT_JSON}} schema {{SCHEMA_JSON}}")
    assert found[0].segment_id == 3 and llm.calls == 2


def test_filter_do_code_quyete_confidence_timing_cooldown_mat_do():
    contexts = [ContextWindow(i, i * 5, i * 5 + 2, (), str(i), ()) for i in range(5)]
    items = [
        opportunity(0, confidence=0.6),       # dưới threshold
        opportunity(1, confidence=0.8, duration=0.6),
        opportunity(2, confidence=0.95, duration=4.0),  # thắng đoạn 1 vì trong cooldown
        opportunity(3, insert=False, confidence=1),
        opportunity(4, confidence=0.7),
    ]
    cfg = FilterSettings(threshold=0.65, cooldown=7, max_per_minute=2,
                         duration_min=0.8, duration_max=2.5, timing_delay=0.15)
    found = filter_opportunities(items, contexts, cfg, video_duration=60)
    assert [item.segment_id for item in found] == [2, 4]
    assert found[0].timing.anchor == 12 and found[0].timing.delay == 0.15
    assert found[0].timing.duration == 2.5


def test_video_ngan_van_cho_phep_mot_co_hoi():
    context = ContextWindow(0, 0, 2, (), "A", ())
    cfg = FilterSettings(0, 0, 2, 0.8, 2.5, 0.15)
    assert len(filter_opportunities([opportunity()], [context], cfg, video_duration=10)) == 1


def test_co_hoi_qua_sat_cuoi_video_bi_bo():
    context = ContextWindow(0, 8.0, 9.5, (), "A", ())
    cfg = FilterSettings(0, 0, 5, 0.8, 2.5, 0.15)
    assert filter_opportunities([opportunity()], [context], cfg, video_duration=10) == []


def test_ollama_adapter_gui_schema_va_tat_thinking():
    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        def chat(self, **kwargs):
            captured["chat"] = kwargs
            return SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))

    result = OllamaLLM("http://local", "qwen", client_factory=Client).complete("p", {"x": 1})
    assert result == '{"ok": true}'
    assert captured["init"] == {"host": "http://local"}
    assert captured["chat"]["format"] == {"x": 1}
    assert captured["chat"]["think"] is False


def test_claude_adapter_gui_structured_output():
    captured = {}

    class Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text='{"ok": true}')])

    def factory():
        return SimpleNamespace(messages=Messages())

    result = ClaudeLLM("claude-test", client_factory=factory).complete("p", {"x": 1})
    assert json.loads(result) == {"ok": True}
    assert captured["output_config"]["format"]["schema"] == {"x": 1}


def test_create_llm_theo_config():
    assert isinstance(create_llm(load_settings(env={})), OllamaLLM)
    settings = load_settings(env={"LLM_BACKEND": "claude"})
    assert isinstance(create_llm(settings), ClaudeLLM)


def test_timing_lam_tron_khong_de_sai_so_float():
    """Lỗi thật khi nghiệm thu: analysis.json ghi duration 1.129999999999999."""
    context = ContextWindow(0, 8.14, 10.4, (), "A", ())
    cfg = FilterSettings(0, 0, 5, 0.8, 2.5, 0.15)
    found = filter_opportunities([opportunity(duration=1.5)], [context], cfg, video_duration=11.68)
    assert found[0].timing.duration == 1.13
