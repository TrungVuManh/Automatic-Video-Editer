"""Phụ đề karaoke .ass — gom dòng, escape, tag \\k, dựng file."""
import re

from pipeline.subtitles import (ass_time, build_ass, build_ass_for_clip, escape_ass, group_lines,
                                karaoke_text, words_in_clip)


def _w(text, start, end):
    return {"w": text, "start": start, "end": end}


# ------------------------------------------------------------------ lọc & gom
def test_words_in_clip_doi_ve_thoi_gian_tuong_doi():
    words = [_w("trước", 5.0, 5.4), _w("xin", 10.2, 10.6), _w("chào", 10.7, 11.2),
             _w("sau", 40.0, 40.5)]
    out = words_in_clip(words, 10.0, 30.0)
    assert [x["w"] for x in out] == ["xin", "chào"]
    assert out[0]["start"] == 0.2 and out[1]["end"] == 1.2


def test_words_in_clip_cat_bot_tu_thua_o_bien():
    out = words_in_clip([_w("dài", 9.5, 10.5)], 10.0, 20.0)
    assert out == [{"w": "dài", "start": 0.0, "end": 0.5}]


def test_words_in_clip_bo_tu_rong():
    assert words_in_clip([_w("  ", 1.0, 1.2), _w("ok", 1.3, 1.5)], 0.0, 5.0) == [
        {"w": "ok", "start": 1.3, "end": 1.5}]


def test_group_lines_ngat_khi_lang():
    words = [_w("a", 0.0, 0.2), _w("b", 0.3, 0.5), _w("c", 2.0, 2.2)]  # lặng 1.5s trước "c"
    lines = group_lines(words, max_tu=5, max_ky_tu=28, ngat_khi_lang=0.6)
    assert [[x["w"] for x in ln] for ln in lines] == [["a", "b"], ["c"]]


def test_group_lines_ngat_khi_du_so_tu():
    words = [_w(f"t{i}", i * 0.2, i * 0.2 + 0.15) for i in range(7)]
    lines = group_lines(words, max_tu=3, max_ky_tu=99, ngat_khi_lang=9)
    assert [len(ln) for ln in lines] == [3, 3, 1]


def test_group_lines_ngat_khi_du_ky_tu():
    words = [_w("mườihaiky", i * 0.2, i * 0.2 + 0.15) for i in range(4)]
    lines = group_lines(words, max_tu=99, max_ky_tu=20, ngat_khi_lang=9)
    assert all(sum(len(x["w"]) for x in ln) <= 20 for ln in lines)
    assert len(lines) > 1


# ------------------------------------------------------------------ định dạng
def test_escape_ky_tu_dieu_khien_ass():
    assert escape_ass("a{b}c\\d") == "a(b)c/d"
    assert escape_ass("hai\ndòng") == "hai dòng"


def test_ass_time():
    assert ass_time(0) == "0:00:00.00"
    assert ass_time(3661.23) == "1:01:01.23"
    assert ass_time(-5) == "0:00:00.00"


def test_karaoke_text_tong_thoi_luong_khop_do_dai_dong():
    line = [_w("xin", 0.0, 0.5), _w("chào", 0.6, 1.0)]
    txt = karaoke_text(line)
    tong_cs = sum(int(n) for n in re.findall(r"\\k(\d+)", txt))
    assert tong_cs == 100                     # 1.0 giây
    assert "xin" in txt and "chào" in txt
    assert "{\\k10}" in txt                   # khoảng lặng 0.1s trước "chào"


def test_karaoke_text_co_dau_cach_giua_cac_tu():
    txt = karaoke_text([_w("a", 0.0, 0.2), _w("b", 0.2, 0.4)])
    assert "a " in txt and not txt.endswith(" ")


def test_karaoke_text_escape_ca_trong_tu():
    txt = karaoke_text([_w("{x}", 0.0, 0.2)])
    assert "(x)" in txt
    # chỉ còn đúng một cặp ngoặc nhọn của chính tag \k
    assert txt.count("{") == 1 and txt.count("}") == 1


# ------------------------------------------------------------------ file .ass
def test_build_ass_du_phan_dau_va_moi_dong_mot_dialogue():
    lines = [[_w("xin", 0.0, 0.5)], [_w("chào", 1.0, 1.5)]]
    out = build_ass(lines, play_w=1080, play_h=1920, font="Arial", co_chu=80, vien=5,
                    canh=8, le_ngang=60, le_doc=200, mau_chinh="&H0000FFFF",
                    mau_phu="&H00FFFFFF", mau_vien="&H00000000")
    assert "PlayResX: 1080" in out and "PlayResY: 1920" in out
    assert out.count("\nDialogue: ") == 2
    assert "Style: Mac,Arial,80," in out
    assert ",8,60,60,200,1" in out            # canh, lề ngang x2, lề dọc


def test_build_ass_for_clip_dat_phu_de_duoi_facecam():
    words = [_w("một", 10.0, 10.4), _w("hai", 10.5, 10.9)]
    out = build_ass_for_clip(words, 10.0, 20.0, {}, "doc", 1080, 1920, le_doc=654)
    assert ",654,1" in out
    assert "Dialogue: 0,0:00:00.00,0:00:00.90" in out


def test_build_ass_khong_co_tu_van_ra_file_hop_le():
    out = build_ass_for_clip([], 0.0, 10.0, {}, "ngang", 1920, 1080)
    assert "[Events]" in out and "Dialogue:" not in out
