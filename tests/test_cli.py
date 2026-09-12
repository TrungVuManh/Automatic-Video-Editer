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
    for cmd in ("doctor", "transcribe", "analyze", "inspect", "render", "run"):
        assert cmd in r.output


@pytest.mark.parametrize("args, buoc", [
    (["analyze", "v.mp4"], "Iteration 3"),
    (["run", "v.mp4"], "Iteration 4"),
])
def test_lenh_chua_lam_bao_ro_va_thoat_ma_1(args, buoc):
    r = runner.invoke(app, args)
    assert r.exit_code == 1
    assert buoc in r.output


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
