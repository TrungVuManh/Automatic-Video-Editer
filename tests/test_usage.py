"""Theo dõi token và chi phí API (jobs/<job>/usage.json)."""
import types

import pipeline.common as common
from pipeline.common import Job, estimate_cost, read_json, record_usage, sum_usage, usage_entry


def test_gia_theo_model():
    # Sonnet 5: $2 / 1M token vào, $10 / 1M token ra
    assert estimate_cost("claude-sonnet-5", 1_000_000, 0) == 2.0
    assert estimate_cost("claude-sonnet-5", 0, 1_000_000) == 10.0
    assert estimate_cost("claude-haiku-4-5", 1_000_000, 0) == 1.0


def test_khop_theo_tien_to_va_model_la():
    # id có hậu tố ngày vẫn phải nhận ra được
    assert estimate_cost("claude-haiku-4-5-20251001", 1_000_000, 0) == 1.0
    # model chưa có trong bảng giá thì trả 0 chứ không nổ
    assert estimate_cost("model-khong-ton-tai", 1_000_000, 999) == 0.0


def test_gia_cache():
    """Đọc từ cache rẻ hơn ~10 lần, ghi vào cache đắt hơn 25%."""
    assert estimate_cost("claude-sonnet-5", 0, 0, cache_read=1_000_000) == 0.2
    assert estimate_cost("claude-sonnet-5", 0, 0, cache_write=1_000_000) == 2.5


def test_usage_entry_chiu_duoc_usage_thieu_truong():
    """SDK cũ (hoặc bản giả lập trong test) không có trường cache — không được nổ."""
    usage = types.SimpleNamespace(input_tokens=1000, output_tokens=200)
    e = usage_entry("select", "claude-sonnet-5", usage)
    assert e["input_tokens"] == 1000 and e["cache_read"] == 0
    assert e["cost_usd"] == estimate_cost("claude-sonnet-5", 1000, 200)


def test_sum_usage_cong_don():
    entries = [usage_entry("a", "claude-sonnet-5", types.SimpleNamespace(input_tokens=10, output_tokens=1)),
               usage_entry("b", "claude-haiku-4-5", types.SimpleNamespace(input_tokens=20, output_tokens=2))]
    total = sum_usage(entries)
    assert total["input_tokens"] == 30 and total["output_tokens"] == 3
    assert total["so_lan_goi"] == 2
    assert total["cost_usd"] == round(sum(e["cost_usd"] for e in entries), 6)


def test_record_usage_ghi_va_cong_don(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "JOBS_DIR", tmp_path)
    job = Job(name="t", streamer="s", platform="twitch")

    record_usage(job, "select", "claude-sonnet-5", types.SimpleNamespace(input_tokens=100, output_tokens=10))
    record_usage(job, "memes", "claude-haiku-4-5", types.SimpleNamespace(input_tokens=50, output_tokens=5))

    data = read_json(job.path("usage.json"))
    assert len(data["lan_goi"]) == 2
    assert data["tong"]["input_tokens"] == 150
    assert [e["step"] for e in data["lan_goi"]] == ["select", "memes"]
