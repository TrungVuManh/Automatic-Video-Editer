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


# ------------------------------------------------------------------ tách đoạn dài theo khoảng lặng
def _tu(text, start, dur=0.3):
    return {"w": text, "start": round(start, 2), "end": round(start + dur, 2)}


def test_tach_doan_dai_tai_khoang_lang():
    """Lỗi thật khi nghiệm thu livestream: đoạn 17 s không dấu câu → meme trễ >10 s."""
    from automeme.analyzer.context import split_long_segments

    words = [_tu(w, 10 + i * 0.35) for i, w in enumerate("ai giữ tiền trong nhà".split())]
    words += [_tu(w, 13 + i * 0.35) for i, w in enumerate("tôi giữ chứ ai".split())]  # lặng ~1 s
    words += [_tu(w, 16 + i * 0.35) for i, w in enumerate("à vợ tôi giữ hộ".split())]
    goc = {"segments": [{"id": 0, "start": 0.0, "end": 5.0, "text": "câu ngắn giữ nguyên"},
                        {"id": 1, "start": 10.0, "end": 17.8, "text": "cả khối dài"}],
           "words": words}
    tach = split_long_segments(goc, max_seconds=4.0, min_pause=0.3)
    assert [s["text"] for s in tach["segments"]] == [
        "câu ngắn giữ nguyên", "ai giữ tiền trong nhà", "tôi giữ chứ ai", "à vợ tôi giữ hộ"]
    assert [s["id"] for s in tach["segments"]] == [0, 1, 2, 3]
    assert tach["segments"][3]["end"] == pytest.approx(17.7)  # neo meme ngay sau câu đùa
    assert len(goc["segments"]) == 2  # không sửa transcript đầu vào


def test_loi_noi_lien_tuc_khong_khoang_lang_van_chia_duoi_nguong():
    from automeme.analyzer.context import split_long_segments

    words = [_tu(f"w{i}", i * 0.3, 0.3) for i in range(40)]  # 12 s nói liền, không nghỉ
    tach = split_long_segments({"segments": [{"id": 0, "start": 0, "end": 12, "text": "x"}],
                                "words": words}, max_seconds=4.0, min_pause=0.3)
    doan = tach["segments"]
    assert all(s["end"] - s["start"] <= 4.0 for s in doan) and len(doan) >= 3
    assert " ".join(s["text"] for s in doan) == " ".join(f"w{i}" for i in range(40))


def test_doan_dai_khong_co_timestamp_tu_thi_giu_nguyen():
    from automeme.analyzer.context import split_long_segments

    goc = {"segments": [{"id": 0, "start": 0, "end": 15, "text": "dài"}], "words": []}
    assert split_long_segments(goc, max_seconds=4, min_pause=0.3)["segments"] == goc["segments"]


def test_mau_cuoi_qua_ngan_gop_vao_mau_truoc():
    """Lỗi thật trên transcript livestream: khoảng lặng ngay trước 1–2 từ cuối làm IndexError."""
    from automeme.analyzer.context import split_long_segments

    words = [_tu(w, 0 + i * 0.35) for i, w in enumerate("một hai ba bốn năm sáu bảy".split())]
    words += [_tu("tám", 2.9)]  # lặng 0.5 s rồi chỉ còn một từ
    tach = split_long_segments({"segments": [{"id": 0, "start": 0, "end": 4.5, "text": "x"}],
                                "words": words}, max_seconds=2.0, min_pause=0.3)
    assert tach["segments"][-1]["text"].endswith("tám")
    assert all(len(s["text"].split()) >= 3 for s in tach["segments"])


def test_im_lang_dai_luon_la_ranh_gioi_du_cau_truoc_ngan():
    """Transcript thật: "này không" … 6 s im lặng … "tắt điện đây" bị gộp thành một câu 7.8 s."""
    from automeme.analyzer.context import split_long_segments

    words = [_tu("này", 16.66, 0.2), _tu("không", 16.88, 0.9),
             _tu("tắt", 24.07, 0.4), _tu("điện", 24.47, 0.3), _tu("đây", 24.83, 0.6)]
    tach = split_long_segments({"segments": [{"id": 0, "start": 16.66, "end": 25.5,
                                              "text": "x"}], "words": words},
                               max_seconds=4.0, min_pause=0.3, min_words=2)
    assert [s["text"] for s in tach["segments"]] == ["này không", "tắt điện đây"]
    assert tach["segments"][0]["end"] == pytest.approx(17.78)


def test_khong_chen_meme_ma_duration_0_van_hop_le():
    """qwen3 trả timing.duration=0 khi insert_meme=false → trước đây bị loại hai lần."""
    from automeme.analyzer.schema import MemeOpportunity

    base = {"segment_id": 2, "confidence": 0.3, "trigger": "", "reason": "", "emotion": "",
            "reaction_type": "", "search_query": "", "preferred_style": "",
            "timing": {"anchor": 5, "delay": 0.1, "duration": 0}}
    assert MemeOpportunity.model_validate({**base, "insert_meme": False}).timing.duration == 0.5
    with pytest.raises(ValueError):
        MemeOpportunity.model_validate({**base, "insert_meme": True, "trigger": "x",
                                        "reason": "x", "emotion": "x", "reaction_type": "x",
                                        "search_query": "x"})
