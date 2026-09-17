"""So khớp từ khóa cho tìm kiếm local (meme, SFX) và cho ranker.

Không dùng `local.tokenize` để so khớp: hàm đó bỏ dấu (đúng cho việc sinh ID/tag từ tên file),
nhưng tiếng Việt bỏ dấu thì "bất ngờ" trùng "nổi bật" + "ngớ ngẩn", "nỗi" trùng "nói", "lộ"
trùng "lo". Ở đây:

- Giữ nguyên dấu. Chỉ khi truy vấn gõ không dấu ("bat ngo") mới so cả hai phía ở dạng bỏ dấu.
- Từ tiếng Việt thường gồm nhiều âm tiết, nên ưu tiên khớp theo cụm liền nhau. Một âm tiết
  khớp lẻ loi trong truy vấn nhiều âm tiết chỉ được nửa điểm ("đau" trong "đau đầu" không đủ
  để coi là khớp "nỗi đau"). Từ tiếng Anh (không dấu) khớp lẻ vẫn đủ điểm.
- Mỗi trường (tag, mô tả…) xét riêng và dấu câu ngắt cụm, để hai tag "bất" và "ngờ" nằm cạnh
  nhau không bị ghép thành "bất ngờ".
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

CUM_TOI_DA = 3            # số âm tiết tối đa của một cụm khi so khớp
DIEM_AM_TIET_LE = 0.5     # điểm cho một âm tiết có dấu khớp lẻ trong truy vấn nhiều âm tiết

_AM_TIET = re.compile(r"[^\W_]+")
_NGAT_CUM = re.compile(r"[,.;:!?/|()\[\]{}\"'\n\t–—-]+")


def bo_dau(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def cac_cum(text: str, *, khong_dau: bool) -> list[list[str]]:
    """Văn bản → danh sách cụm, mỗi cụm là các âm tiết liền nhau (chữ thường, chuẩn NFC)."""
    text = unicodedata.normalize("NFC", text).casefold()
    if khong_dau:
        text = bo_dau(text)
    cum = (_AM_TIET.findall(doan) for doan in _NGAT_CUM.split(text))
    return [am_tiet for am_tiet in cum if am_tiet]


def match_score(query: str, fields: Iterable[str]) -> float:
    """Tỉ lệ 0–1 các âm tiết của `query` được `fields` phủ, ưu tiên khớp theo cụm."""
    khong_dau = bo_dau(query) == query
    cum_truy_van = cac_cum(query, khong_dau=khong_dau)
    tong = sum(len(cum) for cum in cum_truy_van)
    if tong == 0:
        return 0.0

    tu_vung: set[str] = set()
    for field in fields:
        for cum in cac_cum(field, khong_dau=khong_dau):
            for n in range(1, CUM_TOI_DA + 1):
                tu_vung.update(" ".join(cum[i:i + n]) for i in range(len(cum) - n + 1))

    return min(1.0, sum(_diem_cum(cum, tu_vung) for cum in cum_truy_van) / tong)


def _diem_cum(cum: list[str], tu_vung: set[str]) -> float:
    """Chia cụm truy vấn thành các đoạn khớp sao cho tổng điểm lớn nhất (quy hoạch động).

    Tham lam "khớp dài nhất trước" có thể thua: "kế hoạch thất bại" sẽ bị cắt thành
    "kế hoạch thất" + "bại" lẻ thay vì "kế hoạch" + "thất bại".
    """
    m = len(cum)
    tot_nhat = [0.0] * (m + 1)
    for i in range(m - 1, -1, -1):
        tot_nhat[i] = tot_nhat[i + 1]  # bỏ qua âm tiết không khớp
        for n in range(1, min(CUM_TOI_DA, m - i) + 1):
            if " ".join(cum[i:i + n]) not in tu_vung:
                continue
            if n > 1 or m == 1 or cum[i].isascii():
                diem = float(n)
            else:
                diem = DIEM_AM_TIET_LE
            tot_nhat[i] = max(tot_nhat[i], diem + tot_nhat[i + n])
    return tot_nhat[0]
