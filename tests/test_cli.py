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
        "doctor", "transcribe", "analyze", "inspect", "render", "review", "studio",
        "install-memes", "install-gifs", "run",
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
    assert "1 cơ hội dựng" in r.output and "[meme]: shocked reaction" in r.output


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


def test_install_memes_goi_bo_cai_va_in_tom_tat(monkeypatch):
    import automeme.memes.popular as popular_module

    calls = []
    monkeypatch.setattr(
        popular_module,
        "install_popular_memes",
        lambda settings, **kwargs: calls.append(kwargs) or popular_module.InstallResult(
            total=100, installed=98, reused=2, failed=0, errors=[],
        ),
    )
    result = runner.invoke(app, ["install-memes", "--limit", "100"])
    assert result.exit_code == 0
    assert calls == [{"limit": 100}]
    assert "98 tải mới, 2 dùng lại" in result.output


def test_install_gifs_goi_bo_cai_va_in_tom_tat(monkeypatch):
    import automeme.memes.animated as animated_module

    calls = []
    monkeypatch.setattr(
        animated_module,
        "install_animated_gifs",
        lambda settings, **kwargs: calls.append(kwargs) or animated_module.InstallResult(
            total=30, installed=27, reused=3, failed=0, errors=[],
        ),
    )
    result = runner.invoke(app, ["install-gifs", "--limit", "30"])
    assert result.exit_code == 0
    assert calls == [{"limit": 30}]
    assert "27 tải mới, 3 dùng lại" in result.output


# ------------------------------------------------------------------ tải YouTube
def _ket_qua_tai(tmp_path, *, cc=True):
    from automeme.media.youtube import DownloadResult

    return DownloadResult(path=tmp_path / "phim-aqz-KE-bpKQ-30s-60s.mp4", skipped=False, source={
        "title": "Big Buck Bunny", "channel": "Blender", "section": {"start": 30, "end": 60},
        "license": "Creative Commons Attribution" if cc else None, "creative_commons": cc,
    })


def test_download_tai_va_in_tom_tat(monkeypatch, tmp_path):
    import automeme.media.youtube as youtube

    goi = {}

    def gia(url, settings, **kw):
        goi.update(url=url, **kw)
        return _ket_qua_tai(tmp_path, cc=False)

    monkeypatch.setattr(youtube, "download_youtube", gia)
    r = runner.invoke(app, ["download", "https://youtu.be/aqz-KE-bpKQ", "--from", "0:30",
                            "--to", "1:00"])
    assert r.exit_code == 0, r.output
    assert goi["start"] == "0:30" and goi["end"] == "1:00" and goi["force"] is False
    assert "Đã tải:" in r.output and "00:30.00 → 01:00.00" in r.output
    assert "không ghi giấy phép Creative Commons" in r.output
    assert "Tiếp theo: automeme run" in r.output


def test_download_loi_bao_ro_va_thoat_ma_1(monkeypatch):
    import automeme.media.youtube as youtube

    def no(url, settings, **kw):
        raise youtube.DownloadError("Video ở chế độ riêng tư — không tải được.")

    monkeypatch.setattr(youtube, "download_youtube", no)
    r = runner.invoke(app, ["download", "https://youtu.be/aqz-KE-bpKQ"])
    assert r.exit_code == 1 and "riêng tư" in r.output


def test_run_nhan_link_youtube_thi_tai_truoc_roi_chay(monkeypatch, tmp_path):
    import automeme.media.youtube as youtube
    import automeme.pipeline as pipeline
    from automeme.timeline.schema import Timeline

    ket_qua = _ket_qua_tai(tmp_path)
    goi = {}
    monkeypatch.setattr(youtube, "download_youtube",
                        lambda url, settings, **kw: goi.update(tai=(url, kw)) or ket_qua)

    def chay(video, settings, **kw):
        goi["video"] = video
        return tmp_path / "out.mp4", Timeline(video=video.name, events=[])

    monkeypatch.setattr(pipeline, "run_video", chay)
    r = runner.invoke(app, ["run", "youtu.be/aqz-KE-bpKQ", "--from", "0:30", "--to", "1:00"])
    assert r.exit_code == 0, r.output
    assert goi["tai"][1]["start"] == "0:30" and goi["video"] == ket_qua.path


def test_run_file_co_san_kem_from_to_thi_bao_loi(monkeypatch):
    import automeme.pipeline as pipeline

    monkeypatch.setattr(pipeline, "run_video", lambda *a, **k: pytest.fail("không được chạy"))
    r = runner.invoke(app, ["run", "v.mp4", "--from", "0:30"])
    assert r.exit_code == 1 and "chỉ dùng với link YouTube" in r.output
