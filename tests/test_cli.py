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
    (["transcribe", "v.mp4"], "Iteration 1"),
    (["render", "v.mp4"], "Iteration 2"),
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
