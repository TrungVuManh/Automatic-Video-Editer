import unicodedata

import pytest

from automeme.memes.matching import bo_dau, cac_cum, match_score


@pytest.mark.parametrize("query, fields", [
    ("bất ngờ", ["Một thành viên ngớ ngẩn nổi bật"]),   # bỏ dấu thì trùng "ngớ" + "bật"
    ("giấu nỗi đau", ["lời vừa nói"]),                   # "nỗi" ≠ "nói"
    ("tiết lộ", ["lo lắng", "tiệt trùng"]),              # "lộ" ≠ "lo", "tiết" ≠ "tiệt"
])
def test_giu_dau_nen_khong_khop_nham(query, fields):
    assert match_score(query, fields) == 0


def test_truy_van_khong_dau_so_o_dang_bo_dau():
    assert match_score("bat ngo", ["bất ngờ"]) == 1
    assert match_score("Đau", ["dau"]) == 0  # truy vấn có dấu thì phải khớp có dấu


def test_khop_ca_cum_duoc_diem_toi_da():
    assert match_score("kế hoạch thất bại", ["Kế hoạch thất bại thảm hại"]) == 1


def test_chia_cum_toi_uu_chu_khong_tham_lam():
    # "kế hoạch" và "thất bại" ở hai trường khác nhau; tham lam khớp 3 âm tiết đầu sẽ thua
    assert match_score("kế hoạch thất bại", ["kế hoạch thất", "kế hoạch", "thất bại"]) == 1


def test_am_tiet_le_trong_tu_nhieu_am_tiet_chi_nua_diem():
    assert match_score("nỗi đau", ["đau đầu"]) == pytest.approx(0.25)
    assert match_score("nỗi đau", ["cố giấu nỗi đau"]) == 1
    assert match_score("chờ đợi", ["chờ đợi quá lâu"]) > match_score("chờ đợi", ["mong chờ"])


def test_tu_mot_am_tiet_va_tieng_anh_khop_le_van_du_diem():
    assert match_score("sốc", ["tin quá sốc"]) == 1
    assert match_score("awkward silence", ["awkward"]) == pytest.approx(0.5)
    assert match_score("awkward ngượng", ["awkward", "ngượng"]) == pytest.approx(0.75)


def test_khong_ghep_cum_qua_ranh_gioi_truong_hay_dau_cau():
    assert match_score("bất ngờ", ["bất", "ngờ"]) == pytest.approx(0.5)
    assert match_score("bất ngờ", ["hơi bất, ngờ vực"]) == pytest.approx(0.5)


def test_chuan_hoa_unicode_va_hoa_thuong():
    to_hop = unicodedata.normalize("NFD", "Ngượng")  # dấu tách rời như khi copy từ macOS
    assert match_score(to_hop, ["NGƯỢNG ngùng"]) == 1


def test_truy_van_rong_hoac_chi_co_dau_cau():
    assert match_score("", ["gì cũng được"]) == 0
    assert match_score("!!! ...", ["gì cũng được"]) == 0


def test_bo_dau_va_cac_cum():
    assert bo_dau("Đường đi bất ngờ") == "Duong di bat ngo"
    assert cac_cum("Ngượng ngùng, bị nói trúng", khong_dau=False) == [
        ["ngượng", "ngùng"], ["bị", "nói", "trúng"]]
