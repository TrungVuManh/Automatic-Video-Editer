from pathlib import Path

from automeme.transcription.normalize import (
    clean_text,
    format_transcript_summary,
    normalize_transcript,
    validate_transcript,
)

RAW = {
    "language": "vi",
    "duration": 9.0,
    "segments": [
        {"start": 3.32, "end": 5.45, "text": " Ai là người giữ tiền trong nhà? ",
         "words": [{"w": " Ai", "start": 3.32, "end": 3.5},
                   {"w": "là", "start": 3.5, "end": 3.7}]},
        {"start": 0.42, "end": 3.21, "text": "Hôm nay\nchúng ta sẽ hỏi.",
         "words": [{"w": "Hôm", "start": 0.42, "end": 0.6}]},
    ],
}


def test_chuan_hoa_sap_xep_va_danh_lai_id():
    data = normalize_transcript(RAW, video_name="cuoi.mp4", model="large-v3")
    assert [s["id"] for s in data["segments"]] == [0, 1]
    assert data["segments"][0]["text"] == "Hôm nay chúng ta sẽ hỏi."  # xuống dòng thành dấu cách
    assert data["segments"][1]["start"] == 3.32
    assert data["video"] == "cuoi.mp4" and data["model"] == "large-v3"
    assert data["language"] == "vi"


def test_chuan_hoa_gom_va_sap_xep_words():
    data = normalize_transcript(RAW, video_name="v.mp4", model="m")
    assert [w["w"] for w in data["words"]] == ["Hôm", "Ai", "là"]


def test_bo_doan_rong_hoac_thoi_gian_vo_ly():
    raw = {"segments": [
        {"start": 0, "end": 1, "text": "   "},            # rỗng
        {"start": 5, "end": 4, "text": "lùi thời gian"},   # end <= start
        {"start": None, "end": 2, "text": "thiếu start"},
        {"start": 1, "end": 2, "text": "giữ lại"},
    ]}
    data = normalize_transcript(raw, video_name="v.mp4", model="m")
    assert [s["text"] for s in data["segments"]] == ["giữ lại"]


def test_bo_tu_thieu_timestamp():
    raw = {"segments": [{"start": 0, "end": 2, "text": "a b", "words": [
        {"w": "a", "start": 0.1, "end": 0.3},
        {"w": "b", "start": None, "end": 0.9},   # từ không căn được thời gian
        {"w": " ", "start": 1.0, "end": 1.2},    # từ rỗng
    ]}]}
    data = normalize_transcript(raw, video_name="v.mp4", model="m")
    assert [w["w"] for w in data["words"]] == ["a"]


def test_duration_uu_tien_tham_so_roi_moi_den_backend():
    voi_duration = normalize_transcript(RAW, video_name="v.mp4", model="m", duration=47.83)
    assert voi_duration["duration"] == 47.83
    assert normalize_transcript(RAW, video_name="v.mp4", model="m")["duration"] == 9.0
    raw = {"segments": [{"start": 0, "end": 2.5, "text": "x"}]}
    assert normalize_transcript(raw, video_name="v.mp4", model="m")["duration"] == 2.5


def test_clean_text():
    assert clean_text("  a\n b\t c ") == "a b c"
    assert clean_text(None) == ""


def test_validate_bao_khi_khong_co_doan_nao():
    canh_bao = validate_transcript({"segments": [], "words": [], "duration": 5})
    assert len(canh_bao) == 1 and "không nhận được câu nào" in canh_bao[0]


def test_validate_bao_khi_thieu_words():
    canh_bao = validate_transcript(
        {"segments": [{"id": 0, "start": 0, "end": 1, "text": "a"}], "words": [], "duration": 5})
    assert any("timestamp theo từ" in c for c in canh_bao)


def test_validate_bao_doan_vuot_thoi_luong():
    data = {"segments": [{"id": 0, "start": 0, "end": 30, "text": "a"}],
            "words": [{"w": "a", "start": 0, "end": 1}], "duration": 10}
    assert any("vượt quá thời lượng" in c for c in validate_transcript(data))


def test_validate_bao_cau_lap_nhieu_lan():
    data = {"segments": [{"id": i, "start": i, "end": i + 0.5, "text": "Cảm ơn các bạn."}
                         for i in range(4)],
            "words": [{"w": "a", "start": 0, "end": 1}], "duration": 10}
    assert any("lặp liên tiếp" in c for c in validate_transcript(data))


def test_validate_transcript_tot_thi_khong_canh_bao():
    data = {"segments": [{"id": 0, "start": 0.4, "end": 3.2, "text": "a"},
                         {"id": 1, "start": 3.3, "end": 5.4, "text": "b"}],
            "words": [{"w": "a", "start": 0.4, "end": 0.6}], "duration": 9.0}
    assert validate_transcript(data) == []


def test_tom_tat_co_so_lieu_va_vai_dong_dau():
    data = normalize_transcript(RAW, video_name="v.mp4", model="large-v3")
    text = format_transcript_summary(data, Path("data/transcripts/v.json"), so_dong=1)
    assert "2 đoạn" in text and "3 từ" in text and "large-v3" in text
    assert "[00:00.42] Hôm nay chúng ta sẽ hỏi." in text
    assert "còn 1 đoạn nữa" in text
    assert "data" in text and "v.json" in text


# ------------------------------------------------------------------ lọc câu Whisper bịa
def _loc(segments, words=(), **kw):
    from automeme.transcription.normalize import drop_hallucinations

    cfg = {"phrases": ["cảm ơn các bạn đã theo dõi", "đăng ký kênh"],
           "max_words_per_second": 10, "no_speech_threshold": 0.6, **kw}
    return drop_hallucinations({"segments": segments, "words": list(words)}, **cfg)


def test_bo_cau_bia_noi_nhanh_vo_ly():
    """Lỗi thật trên livestream: 10 từ trong 0,04 giây ở cuối đoạn im lặng."""
    that = {"id": 0, "start": 84.32, "end": 89.88, "text": "hai nền tảng thì nó giúp nó dễ"}
    bia = {"id": 1, "start": 89.88, "end": 89.92,
           "text": "Cảm ơn các bạn đã theo dõi và hẹn gặp lại."}
    words = [{"w": "dễ", "start": 89.74, "end": 89.87}, {"w": "và", "start": 89.88, "end": 89.92}]
    moi, bo = _loc([that, bia], words)
    assert [s["text"] for s in moi["segments"]] == [that["text"]]
    assert bo == [bia] and [w["w"] for w in moi["words"]] == ["dễ"]


def test_cau_quen_thuoc_noi_binh_thuong_thi_giu():
    """Streamer có thể nói thật lời chào cuối — chỉ bỏ khi có thêm dấu hiệu bịa."""
    chao = {"id": 0, "start": 10, "end": 13, "text": "cảm ơn các bạn đã theo dõi nhé"}
    moi, bo = _loc([chao])
    assert bo == [] and moi["segments"] == [chao]
    im_lang = {**chao, "no_speech_prob": 0.9}
    assert _loc([im_lang])[1] == [im_lang]  # Whisper tự báo nhiều khả năng không có tiếng nói


def test_cau_ngan_hop_le_khong_bi_bo_va_danh_lai_id():
    ngan = {"id": 0, "start": 1.0, "end": 1.1, "text": "ừ"}  # 1 từ, dưới ngưỡng 4 từ
    sau = {"id": 1, "start": 2.0, "end": 2.05, "text": "Đăng ký kênh ủng hộ mình nha các bạn"}
    tiep = {"id": 2, "start": 3.0, "end": 4.0, "text": "đi thôi"}
    moi, bo = _loc([ngan, sau, tiep])
    assert [s["id"] for s in moi["segments"]] == [0, 1] and bo == [sau]
    assert _loc([ngan])[0]["segments"] == [ngan]


def test_chuan_hoa_giu_xac_suat_khong_co_tieng_noi():
    raw = {"segments": [{"start": 0, "end": 1, "text": "a", "no_speech_prob": 0.12345,
                         "avg_logprob": -0.5}, {"start": 1, "end": 2, "text": "b"}]}
    doan = normalize_transcript(raw, video_name="v.mp4", model="m")["segments"]
    assert doan[0]["no_speech_prob"] == 0.123 and "no_speech_prob" not in doan[1]


def test_bo_cau_quen_thuoc_lap_lai_nhieu_lan():
    """Thí nghiệm gợi ý từ vựng: Whisper bịa cùng một câu cho cả 90 giây."""
    bia = "Hãy subscribe cho kênh lalaschool Để không bỏ lỡ những video hấp dẫn"
    segs = [{"id": i, "start": t, "end": t + 30, "text": bia} for i, t in enumerate((0, 48, 77))]
    moi, bo = _loc(segs, phrases=["lalaschool"])
    assert moi["segments"] == [] and len(bo) == 3
    mot_lan = [{**segs[0], "text": "hãy subscribe cho kênh lalaschool nhé"}]
    assert _loc(mot_lan, phrases=["lalaschool"])[1] == []  # một lần, tốc độ bình thường → giữ
