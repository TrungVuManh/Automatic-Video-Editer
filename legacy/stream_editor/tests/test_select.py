from pipeline.s4_select import candidate_text, snap_to_words, validate_clips

CANDS = [{"id": "k01", "start": 100.0, "end": 190.0, "peaks": [160.0], "score": 1.0},
         {"id": "k02", "start": 500.0, "end": 590.0, "peaks": [560.0], "score": 0.8}]
CCFG = {"min_sec": 15, "max_sec": 90, "max_clips": 10}


def _clip(cid, s, e, diem=7):
    return {"candidate_id": cid, "start": s, "end": e, "loai": "hài", "diem": diem,
            "tieu_de": "t", "hook": "h", "ly_do": "l"}


def test_rejects_fake_id_bad_length_and_overlap():
    raw = [_clip("k01", 120, 170), _clip("k99", 0, 30), _clip("k02", 500, 505),
           _clip("k01", 150, 185)]
    ok, problems = validate_clips(raw, CANDS, CCFG)
    assert [c["id"] for c in ok] == ["c01"]
    assert len(problems) == 3


def test_clamps_to_candidate_bounds():
    ok, _ = validate_clips([_clip("k02", 450, 600)], CANDS, CCFG)
    assert ok[0]["start"] == 495.0 and ok[0]["end"] == 595.0


def test_keeps_best_when_over_limit():
    raw = [_clip("k01", 110, 150, diem=4), _clip("k02", 510, 560, diem=9)]
    ok, _ = validate_clips(raw, CANDS, {**CCFG, "max_clips": 1})
    assert len(ok) == 1 and ok[0]["diem"] == 9


def test_snap_to_words():
    words = [{"w": "xin", "start": 9.8, "end": 10.4}, {"w": "chào", "start": 29.5, "end": 30.2}]
    c = snap_to_words({"start": 10.0, "end": 30.0}, words)
    assert c["start"] == round(9.8 - 0.15, 2) and c["end"] == round(30.2 + 0.35, 2)


def test_candidate_text_contains_chat_and_transcript():
    segs = [{"start": 150.0, "end": 155.0, "text": "ối dồi ôi"}]
    chat = [{"t": 158.0, "user": "a", "text": "KKK"}]
    txt = candidate_text(CANDS[0], segs, chat)
    assert "k01" in txt and "ối dồi ôi" in txt and "KKK" in txt


def test_candidate_text_groups_spam():
    chat = [{"t": 160.0 + i * 0.1, "user": "u", "text": "KKKK"} for i in range(40)]
    txt = candidate_text(CANDS[0], [], chat)
    assert txt.count("KKKK") == 1 and "×40" in txt
