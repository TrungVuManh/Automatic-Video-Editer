import automeme.doctor as doctor
from automeme.config import load_settings
from automeme.doctor import (
    FAIL,
    OK,
    WARN,
    check_environment,
    format_checks,
    has_model,
    ollama_model_names,
    parse_nvidia_smi,
)


def test_format_checks_tach_hong_va_thieu():
    text = format_checks([
        ("Python", OK, "3.11"),
        ("ffmpeg", FAIL, "không thấy"),
        ("Ollama", WARN, "chưa chạy"),
    ])
    assert "CẦN SỬA — ffmpeg" in text
    assert "Thiếu nhưng chưa chặn: Ollama" in text
    assert "[ HỎNG ]" in text


def test_format_checks_tat_ca_dat():
    text = format_checks([("Python", OK, "3.11")])
    assert "tất cả đạt" in text
    assert "Thiếu" not in text


def test_parse_nvidia_smi():
    out = "NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB\nTesla T4, 15360 MiB\n"
    assert parse_nvidia_smi(out) == ["NVIDIA GeForce RTX 4060 Laptop GPU (8188 MiB)",
                                     "Tesla T4 (15360 MiB)"]
    assert parse_nvidia_smi("") == []


def test_ollama_model_names_va_has_model():
    tags = {"models": [{"name": "qwen3:8b"}, {"model": "llama3:latest"}, {}]}
    names = ollama_model_names(tags)
    assert names == ["qwen3:8b", "llama3:latest"]
    assert has_model(names, "qwen3:8b")
    assert has_model(names, "llama3")  # không ghi tag = :latest
    assert not has_model(names, "qwen3:4b")
    assert ollama_model_names({}) == []


def _gia_lap_may(monkeypatch):
    monkeypatch.setattr(doctor, "gpu_names", lambda: [])
    monkeypatch.setattr(doctor, "ollama_status", lambda host, model: ("Ollama", WARN, "giả lập"))


def test_check_environment_khong_nem_loi(monkeypatch):
    _gia_lap_may(monkeypatch)
    rows = check_environment(load_settings(env={}))
    names = [name for name, _, _ in rows]
    assert "Cấu hình" in names and "Ollama" in names and "ffmpeg" in names
    assert dict((n, s) for n, s, _ in rows)["Cấu hình"] == OK


def test_check_environment_bao_loi_cau_hinh(monkeypatch):
    _gia_lap_may(monkeypatch)
    rows = check_environment(None, config_error="Không có profile 'x'")
    status = dict((n, s) for n, s, _ in rows)
    assert status["Cấu hình"] == FAIL
    assert "Ollama" not in status  # không có cấu hình thì không biết địa chỉ Ollama


def test_backend_claude_thieu_key_la_hong(monkeypatch):
    _gia_lap_may(monkeypatch)
    monkeypatch.setattr(doctor, "read_env", lambda: {})
    monkeypatch.setattr(doctor, "_importable", lambda m: True)
    rows = check_environment(load_settings(env={"LLM_BACKEND": "claude"}))
    status = dict((n, s) for n, s, _ in rows)
    assert status["Claude API"] == FAIL
    assert "Ollama" not in status
