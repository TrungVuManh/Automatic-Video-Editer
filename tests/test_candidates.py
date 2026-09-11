import numpy as np

from pipeline.s3_candidates import combine, compute_signals, expand_and_merge, pick_peaks

CFG = dict(window=10, chat_tokens=["kkk", "gg"], speech_keywords=["ối", "sao lại thế"])
W = {"chat": 0.5, "loudness": 0.3, "keywords": 0.2}


def _fake_stream(duration=3600, seed=0):
    rng = np.random.default_rng(seed)
    loud = list(-30 + rng.normal(0, 1.5, duration))
    for t in range(1800, 1808):          # streamer hét lúc 30:00
        loud[t] = -8.0
    chat = [{"t": float(t), "user": "u", "text": "hello"} for t in rng.uniform(0, duration, 1500)]
    chat += [{"t": 605.0 + i * 0.1, "user": "u", "text": "KKKKK"} for i in range(60)]   # chat bùng lúc 10:05
    return loud, chat


def test_finds_chat_spike_and_loud_spike():
    loud, chat = _fake_stream()
    sig = compute_signals(loudness=loud, chat=chat, words=[], **CFG)
    score = combine(sig, W, 10, 300)
    peaks = [p * 10 for p in pick_peaks(score, 10, top_k=5, min_gap_sec=60)]
    assert any(600 <= t <= 610 for t in peaks)
    assert any(1800 <= t <= 1810 for t in peaks)


def test_works_without_chat():
    loud, _ = _fake_stream()
    sig = compute_signals(loudness=loud, chat=None, words=[], **CFG)
    score = combine(sig, W, 10, 300)
    peaks = [p * 10 for p in pick_peaks(score, 10, top_k=3, min_gap_sec=60)]
    assert any(1800 <= t <= 1810 for t in peaks)


def test_keyword_whole_word_only():
    words = [{"w": "tối", "start": 100.0, "end": 100.3},      # không được khớp "ối"
             {"w": "Ối!", "start": 200.0, "end": 200.3},
             {"w": "sao", "start": 300.0, "end": 300.2},
             {"w": "lại", "start": 300.2, "end": 300.4},
             {"w": "thế", "start": 300.4, "end": 300.6}]
    sig = compute_signals(loudness=[-30.0] * 400, chat=None, words=words, **CFG)
    assert sig["keywords"][10] == 0
    assert sig["keywords"][20] == 1
    assert sig["keywords"][30] == 1


def test_min_gap_and_merge():
    score = np.zeros(100)
    score[[20, 22, 60]] = [1.0, 0.9, 0.8]
    peaks = pick_peaks(score, 10, top_k=10, min_gap_sec=60)
    assert peaks == [20, 60]              # đỉnh 22 quá gần đỉnh 20
    cands = expand_and_merge([20, 26], score, 10, pre=60, post=30, duration=1000)
    assert len(cands) == 1 and cands[0]["id"] == "k01"
    assert cands[0]["start"] == 145.0 and cands[0]["end"] == 295.0


def test_bo_cua_so_cuoi_khi_qua_ngan():
    """Cửa sổ cuối VOD thiếu dữ liệu (chat = 0, âm lượng lệch) hay tạo đỉnh giả."""
    # 3603 giây: cửa sổ cuối chỉ dài 3s < nửa cửa sổ (5s) -> bỏ
    sig = compute_signals(loudness=[-30.0] * 3603, chat=None, words=[], **CFG)
    assert len(sig["loudness"]) == 360

    # 3608 giây: cửa sổ cuối dài 8s >= 5s -> giữ, đệm cho đủ
    sig = compute_signals(loudness=[-30.0] * 3608, chat=None, words=[], **CFG)
    assert len(sig["loudness"]) == 361
