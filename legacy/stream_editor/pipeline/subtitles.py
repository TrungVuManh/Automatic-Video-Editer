"""Dựng file phụ đề .ass có hiệu ứng tô chữ theo lời nói (karaoke).

Tất cả là hàm thuần: từ `words.json` (timestamp theo từ) ra chuỗi nội dung file .ass.
Việc burn vào video do `s7_render.py` làm.

Nguyên tắc màu trong ASS karaoke: chữ hiện ra bằng `SecondaryColour`, tag `\\k` quét tới
đâu thì đổi sang `PrimaryColour` tới đó. Nên `mau_chinh` là màu chữ đã/đang được nói.
Màu viết theo &HAABBGGRR (BGR chứ không phải RGB).
"""
from __future__ import annotations

# Kiểu chữ mặc định cho từng định dạng; ghi đè trong config/settings.yaml → phu_de
STYLE_MAC_DINH = {
    "font": "Arial",
    "mau_chinh": "&H0000FFFF",   # vàng — chữ đã được nói
    "mau_phu": "&H00FFFFFF",     # trắng — chữ chưa tới
    "mau_vien": "&H00000000",    # đen
    "max_tu": 5,
    "max_ky_tu": 28,
    "ngat_khi_lang": 0.6,
    "doc": {"co_chu": 80, "vien": 5, "canh": 8, "le_ngang": 60, "le_doc": 40},
    "ngang": {"co_chu": 52, "vien": 4, "canh": 2, "le_ngang": 80, "le_doc": 70},
}


# ------------------------------------------------------------------ chuẩn bị từ
def words_in_clip(words: list[dict], start: float, end: float) -> list[dict]:
    """Lọc các từ nằm trong [start, end] và đổi về thời gian tương đối so với đầu clip."""
    out = []
    for w in words:
        if w["end"] <= start or w["start"] >= end:
            continue
        text = str(w["w"]).strip()
        if not text:
            continue
        s = max(0.0, w["start"] - start)
        e = min(end - start, w["end"] - start)
        if e > s:
            out.append({"w": text, "start": round(s, 3), "end": round(e, 3)})
    return out


def group_lines(words: list[dict], max_tu: int = 5, max_ky_tu: int = 28,
                ngat_khi_lang: float = 0.6) -> list[list[dict]]:
    """Gom từ thành dòng: ngắt khi đủ số từ, đủ ký tự, hoặc có khoảng lặng dài."""
    lines: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        if cur:
            lang = w["start"] - cur[-1]["end"]
            so_ky_tu = sum(len(x["w"]) for x in cur) + len(cur) + len(w["w"])
            if lang > ngat_khi_lang or len(cur) >= max_tu or so_ky_tu > max_ky_tu:
                lines.append(cur)
                cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    return lines


# ------------------------------------------------------------------ định dạng ASS
def escape_ass(text: str) -> str:
    """`{`, `}`, `\\` là ký tự điều khiển của ASS và libass không có cách escape đáng tin cậy,
    nên đổi sang ký tự nhìn tương đương. Xuống dòng đổi thành dấu cách."""
    return (text.replace("\\", "/")
                .replace("{", "(")
                .replace("}", ")")
                .replace("\r", " ")
                .replace("\n", " "))


def ass_time(sec: float) -> str:
    """Thời gian ASS: H:MM:SS.cc"""
    cs = int(round(max(0.0, sec) * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def karaoke_text(line: list[dict]) -> str:
    """Một dòng thành chuỗi có tag \\k: mỗi từ kèm thời lượng tính bằng phần trăm giây.

    Khoảng lặng trước một từ được đưa vào một tag \\k rỗng để chữ không sáng sớm.
    """
    parts = []
    cursor = line[0]["start"]
    for i, w in enumerate(line):
        lang = w["start"] - cursor
        if lang >= 0.01:
            parts.append("{\\k%d}" % round(lang * 100))
        dur = max(0.01, w["end"] - w["start"])
        duoi = "" if i == len(line) - 1 else " "
        parts.append("{\\k%d}%s%s" % (round(dur * 100), escape_ass(w["w"]), duoi))
        cursor = w["end"]
    return "".join(parts)


def build_ass(lines: list[list[dict]], *, play_w: int, play_h: int, font: str,
              co_chu: int, vien: int, canh: int, le_ngang: int, le_doc: int,
              mau_chinh: str, mau_phu: str, mau_vien: str) -> str:
    """Nội dung đầy đủ của một file .ass.

    `canh` theo quy ước ASS: 2 = giữa-dưới, 8 = giữa-trên. `le_doc` là MarginV, tính từ
    đáy khi canh 1/2/3 và từ đỉnh khi canh 7/8/9.
    """
    head = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {play_w}",
        f"PlayResY: {play_h}",
        "WrapStyle: 2",           # chỉ xuống dòng ở chỗ ta chỉ định
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Mac,{font},{co_chu},{mau_chinh},{mau_phu},{mau_vien},&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,{vien},2,{canh},{le_ngang},{le_ngang},{le_doc},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    events = [
        f"Dialogue: 0,{ass_time(line[0]['start'])},{ass_time(line[-1]['end'])},Mac,,0,0,0,,"
        f"{karaoke_text(line)}"
        for line in lines if line
    ]
    return "\n".join(head + events) + "\n"


def build_ass_for_clip(words: list[dict], start: float, end: float, style: dict,
                       dinh_dang: str, play_w: int, play_h: int,
                       le_doc: int | None = None) -> str:
    """Gộp các bước: lọc từ trong clip → gom dòng → dựng .ass cho một định dạng.

    `le_doc` khác None sẽ ghi đè lề dọc — dùng để đặt phụ đề ngay dưới facecam.
    """
    cfg = {**STYLE_MAC_DINH, **(style or {})}
    khung = {**STYLE_MAC_DINH[dinh_dang], **(cfg.get(dinh_dang) or {})}
    lines = group_lines(words_in_clip(words, start, end),
                        max_tu=cfg["max_tu"], max_ky_tu=cfg["max_ky_tu"],
                        ngat_khi_lang=cfg["ngat_khi_lang"])
    return build_ass(lines, play_w=play_w, play_h=play_h, font=cfg["font"],
                     co_chu=khung["co_chu"], vien=khung["vien"], canh=khung["canh"],
                     le_ngang=khung["le_ngang"],
                     le_doc=khung["le_doc"] if le_doc is None else le_doc,
                     mau_chinh=cfg["mau_chinh"], mau_phu=cfg["mau_phu"], mau_vien=cfg["mau_vien"])
