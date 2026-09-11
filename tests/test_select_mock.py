"""Kiểm tra toàn bộ bước 4 với Claude giả lập (không cần API key)."""
import sys
import types

import pipeline.common as common
from pipeline.common import Job, load_settings, load_streamer, read_json, write_json


class _FakeClient:
    def __init__(self, *a, **k):
        self.messages = self
        self.last_prompt = None

    def create(self, **kwargs):
        assert kwargs["tool_choice"]["name"] == "submit_clips"
        _FakeClient.last_prompt = kwargs["messages"][0]["content"]
        block = types.SimpleNamespace(type="tool_use", input={"clips": [
            {"candidate_id": "k01", "start": 120, "end": 160, "loai": "hài", "diem": 8,
             "tieu_de": "Ối dồi ôi", "hook": "Không ai ngờ...", "ly_do": "chat bùng"},
            {"candidate_id": "k77", "start": 0, "end": 30, "loai": "fail", "diem": 5,
             "tieu_de": "x", "hook": "x", "ly_do": "id bịa"},
        ]})
        usage = types.SimpleNamespace(input_tokens=1000, output_tokens=200)
        return types.SimpleNamespace(content=[block], usage=usage)


def test_select_clips_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "JOBS_DIR", tmp_path)
    monkeypatch.setattr(common, "FEEDBACK_FILE", tmp_path / "fb.jsonl")
    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=_FakeClient))
    import pipeline.s4_select as s4
    monkeypatch.setattr(s4, "FEEDBACK_FILE", tmp_path / "fb.jsonl")

    job = Job(name="t", streamer="streamer_example", platform="twitch")
    write_json(job.candidates, [{"id": "k01", "start": 100.0, "end": 190.0, "peaks": [160.0], "score": 1.0}])
    write_json(job.segments, [{"start": 150.0, "end": 155.0, "text": "sao lại thế"}])
    write_json(job.words, [{"w": "thế", "start": 159.8, "end": 160.3}])

    clips = s4.select_clips(job, load_settings(), load_streamer("streamer_example"))
    assert len(clips) == 1 and clips[0]["id"] == "c01"
    assert clips[0]["end"] == round(160.3 + 0.35, 2)          # đã kéo ra hết từ
    assert read_json(job.clips) == clips
    assert "sao lại thế" in _FakeClient.last_prompt
    assert "Streamer Mẫu" in _FakeClient.last_prompt
