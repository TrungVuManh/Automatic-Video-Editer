import os
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from automeme.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _khong_ghi_file_log(monkeypatch):
    """Test CLI không ghi vào data/logs/ thật của dự án."""
    monkeypatch.setattr("automeme.cli.add_file_log", lambda path: path)


def test_help_liet_ke_du_lenh():
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0
    for cmd in (
        "doctor", "transcribe", "analyze", "inspect", "render", "review", "studio", "run",
    ):
        assert cmd in r.output


def test_help_khong_vo_khi_console_ban_dau_la_cp1252():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252"
    result = subprocess.run(
        [sys.executable, "-m", "automeme", "--help"],
        env=env,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "automeme" in result.stdout.decode("utf-8")

def test_doctor_profile_sai_thoat_ma_1():
    r = runner.invoke(app, ["doctor", "--profile", "khong_co"])
    assert r.exit_code == 1
    assert "Không có profile" in r.output


def test_transcribe_goi_pipeline_va_in_tom_tat(monkeypatch, tmp_path):
    import automeme.pipeline as pipeline

    data = {"segments": [{"id": 0, "start": 0.4, "end": 1.0, "text": "Vợ tôi giữ hộ."}],
            "words": [{"w": "Vợ", "start": 0.4, "end": 0.6}], "duration": 1.0,
            "model": "large-v3"}
    monkeypatch.setattr(pipeline, "transcribe_video",
                        lambda video, settings, **kw: (tmp_path / "v.json", data))
    r = runner.invoke(app, ["transcribe", "v.mp4"])
    assert r.exit_code == 0
    assert "1 đoạn, 1 từ" in r.output
    assert "Vợ tôi giữ hộ." in r.output


def test_transcribe_bao_loi_ro_rang_va_thoat_ma_1(monkeypatch):
    import automeme.pipeline as pipeline

    def no(video, settings, **kw):
        raise RuntimeError("Chưa cài faster-whisper.")

    monkeypatch.setattr(pipeline, "transcribe_video", no)
    r = runner.invoke(app, ["transcribe", "v.mp4"])
    assert r.exit_code == 1
    assert "Chưa cài faster-whisper." in r.output


def test_transcribe_profile_sai_thoat_ma_1():
    r = runner.invoke(app, ["transcribe", "v.mp4", "--profile", "khong_co"])
    assert r.exit_code == 1
    assert "Không có profile" in r.output


def test_analyze_goi_pipeline_va_in_tom_tat(monkeypatch, tmp_path):
    import automeme.pipeline as pipeline
    from automeme.analyzer.schema import Analysis

    analysis = Analysis.model_validate({
        "video": "v.mp4",
        "backend": "ollama",
        "model": "qwen3:8b",
        "opportunities": [{
            "segment_id": 2,
            "insert_meme": True,
            "confidence": 0.9,
            "trigger": "punchline",
            "reason": "bất ngờ",
            "emotion": "sốc",
            "reaction_type": "shock",
            "search_query": "shocked reaction",
            "preferred_style": "reaction",
            "timing": {"anchor": 2.0, "delay": 0.15, "duration": 1.5},
        }],
    })
    monkeypatch.setattr(pipeline, "analyze_video",
                        lambda video, settings, **kw: (tmp_path / "v.json", analysis))
    r = runner.invoke(app, ["analyze", "v.mp4", "--force"])
    assert r.exit_code == 0
    assert "1 cơ hội meme" in r.output and "shocked reaction" in r.output


def test_analyze_bao_loi_ro_rang(monkeypatch):
    import automeme.pipeline as pipeline

    def no(video, settings, **kw):
        raise RuntimeError("Không gọi được Ollama")

    monkeypatch.setattr(pipeline, "analyze_video", no)
    r = runner.invoke(app, ["analyze", "v.mp4"])
    assert r.exit_code == 1
    assert "Không gọi được Ollama" in r.output


def test_run_goi_pipeline_va_in_ket_qua(monkeypatch, tmp_path):
    import automeme.pipeline as pipeline
    from automeme.timeline.schema import MemeEvent, Timeline

    timeline = Timeline(video="v.mp4", events=[
        MemeEvent(id="event_001", start=1, duration=1, asset="a.png"),
    ])
    monkeypatch.setattr(pipeline, "run_video",
                        lambda video, settings, **kw: (tmp_path / "out.mp4", timeline))
    r = runner.invoke(app, ["run", "v.mp4", "--profile", "funny", "--force"])
    assert r.exit_code == 0
    assert "Hoàn tất: 1 meme" in r.output and "out.mp4" in r.output


def test_run_bao_loi_ro_rang(monkeypatch):
    import automeme.pipeline as pipeline

    def no(video, settings, **kw):
        raise RuntimeError("Không có meme phù hợp")

    monkeypatch.setattr(pipeline, "run_video", no)
    r = runner.invoke(app, ["run", "v.mp4"])
    assert r.exit_code == 1 and "Không có meme phù hợp" in r.output


def test_review_tao_session_va_mo_server(monkeypatch):
    import automeme.review.server as server_module
    import automeme.review.service as service_module

    sentinel = object()
    calls = []
    monkeypatch.setattr(service_module, "create_review_session", lambda *a, **kw: sentinel)
    monkeypatch.setattr(
        server_module,
        "serve_review",
        lambda session, **kw: calls.append((session, kw)),
    )
    result = runner.invoke(app, [
        "review", "v.mp4", "--port", "0", "--no-browser", "--profile", "funny",
    ])
    assert result.exit_code == 0
    assert calls == [(sentinel, {"port": 0, "open_browser": False})]


def test_studio_tao_service_va_mo_server(monkeypatch):
    import automeme.studio.server as server_module

    calls = []
    monkeypatch.setattr(
        server_module,
        "serve_studio",
        lambda service, **kw: calls.append((service, kw)),
    )
    result = runner.invoke(app, [
        "studio", "--port", "0", "--no-browser", "--profile", "funny",
    ])
    assert result.exit_code == 0
    assert calls[0][1] == {"port": 0, "open_browser": False}
    assert calls[0][0].settings.editing.max_memes_per_minute == 5
