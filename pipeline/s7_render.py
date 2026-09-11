r"""Bước 7 — Render clip đã duyệt (ngang và/hoặc dọc, có phụ đề karaoke) + ghép highlight.

Với mỗi clip và mỗi định dạng:
  cắt chính xác (encode lại) → layout (dọc thì facecam trên / gameplay dưới) → phụ đề .ass.

Ghi chú Windows: FFmpeg được chạy với `cwd` là thư mục chứa file .ass và nhận tên file
tương đối, nên không phải escape `:` và `\` trong filter — nguồn lỗi kinh điển.
"""
from __future__ import annotations

import os
from pathlib import Path

from .common import FONTS_DIR, Job, log, probe_video_size, read_json, require_binary, run_cmd
from .layout import build_filter_from_layout, compute_vertical_layout
from .subtitles import build_ass_for_clip

DINH_DANG = {"ngang", "doc"}


def render(job: Job, settings: dict, streamer: dict | None = None, preview: bool = False,
           include_pending: bool = False, dinh_dang: str | None = None) -> list[Path]:
    require_binary("ffmpeg")
    rcfg = settings["render"]
    streamer = streamer or {}

    clips = read_json(job.clips)
    chosen = [c for c in clips if c.get("approved") or (include_pending and c.get("approved") is None)]
    if not chosen:
        log.warning("Chưa có clip nào được duyệt. Chạy `python run.py review --job %s` trước.", job.name)
        return []

    formats = parse_formats(dinh_dang or rcfg.get("dinh_dang", "ngang"))
    words = read_json(job.words) if job.words.exists() else []
    dung_phu_de = bool(rcfg.get("phu_de", True)) and bool(words)
    if rcfg.get("phu_de", True) and not words:
        log.warning("Không có words.json — render không phụ đề. Xem lại bước preprocess.")

    src_w, src_h = probe_video_size(job.video)
    layout = compute_vertical_layout(src_w, src_h, streamer)
    if "doc" in formats and layout.get("canh_bao"):
        log.warning("Layout dọc: %s", layout["canh_bao"])
    log.info("Nguồn %dx%d — render %d clip, định dạng: %s%s",
             src_w, src_h, len(chosen), ", ".join(formats), " (có phụ đề)" if dung_phu_de else "")

    out_dir = job.path("preview" if preview else "final", "x").parent
    ket_qua: list[Path] = []
    for fmt in formats:
        outputs = []
        for c in chosen:
            out = out_dir / f"{c['id']}_{fmt}.mp4"
            if out.exists():
                log.info("Đã có %s, bỏ qua.", out.name)
                outputs.append(out)
                continue
            ass = _viet_ass(job, c, fmt, words, settings, layout) if dung_phu_de else None
            log.info("Render %s %s (%.0fs)...", c["id"], fmt, c["end"] - c["start"])
            _render_mot_clip(job, c, out, fmt, layout, rcfg, ass, preview)
            outputs.append(out)
        ket_qua += outputs
        if len(outputs) > 1:
            _concat(outputs, out_dir / f"highlight_{fmt}.mp4")

    log.info("Bước 7 xong: %d file → %s", len(ket_qua), out_dir)
    return ket_qua


def parse_formats(value: str) -> list[str]:
    """`ngang` | `doc` | `ca-hai` → danh sách định dạng cần render."""
    value = (value or "ngang").strip().lower()
    if value in ("ca-hai", "ca_hai", "cahai", "both"):
        return ["ngang", "doc"]
    if value not in DINH_DANG:
        raise ValueError(f"Định dạng không hợp lệ: {value}. Chọn ngang | doc | ca-hai.")
    return [value]


# ------------------------------------------------------------------ filtergraph
def build_render_filter(fmt: str, layout: dict, ass_name: str | None = None,
                        cao_preview: int | None = None, fontsdir: str | None = None) -> str:
    r"""filter_complex hoàn chỉnh cho một clip; nhãn video ra luôn là [v].

    Hàm thuần. `ass_name` và `fontsdir` đều là đường dẫn TƯƠNG ĐỐI so với thư mục chứa
    file .ass (FFmpeg được chạy với cwd ở đó), nên trong chuỗi filter không có `:` hay `\`
    — hai ký tự phải escape trên Windows.
    """
    steps = [build_filter_from_layout(layout, nhan_ra="base") if fmt == "doc"
             else "[0:v]setsar=1[base]"]

    hau = []
    if cao_preview:
        hau.append(f"scale=-2:{cao_preview}")
    if ass_name:
        # Burn sau khi thu nhỏ: libass tự co giãn theo PlayResX/Y nên chữ vẫn đúng vị trí.
        hau.append(f"ass={ass_name}" + (f":fontsdir={fontsdir}" if fontsdir else ""))
    steps.append(f"[base]{','.join(hau)}[v]" if hau else "[base]null[v]")
    return ";".join(steps)


def fontsdir_tuong_doi(subs_dir: Path) -> str | None:
    r"""Đường dẫn tương đối tới assets/fonts/ nếu thư mục đó có font.

    Dùng đường dẫn tương đối + dấu `/` để chuỗi filter không chứa ổ đĩa (`C:`) hay `\`.
    """
    if not FONTS_DIR.is_dir():
        return None
    if not any(p.suffix.lower() in (".ttf", ".otf", ".ttc") for p in FONTS_DIR.iterdir()):
        return None
    return os.path.relpath(FONTS_DIR, subs_dir).replace("\\", "/")


def le_doc_phu_de(fmt: str, layout: dict, style: dict) -> int | None:
    """Với khung dọc, đặt phụ đề ngay dưới facecam thay vì dùng lề cố định."""
    if fmt != "doc" or not layout.get("h_cam"):
        return None
    them = (style.get("doc") or {}).get("le_doc", 40)
    return int(layout["h_cam"]) + int(them)


# ------------------------------------------------------------------ FFmpeg
def _viet_ass(job: Job, c: dict, fmt: str, words: list[dict], settings: dict,
              layout: dict) -> Path:
    style = settings.get("phu_de") or {}
    play_w, play_h = (layout["out_w"], layout["out_h"]) if fmt == "doc" else (1920, 1080)
    noi_dung = build_ass_for_clip(words, c["start"], c["end"], style, fmt,
                                  play_w, play_h, le_doc=le_doc_phu_de(fmt, layout, style))
    path = job.path("subs", f"{c['id']}_{fmt}.ass")
    path.write_text(noi_dung, encoding="utf-8")
    return path


def _render_mot_clip(job: Job, c: dict, out: Path, fmt: str, layout: dict, rcfg: dict,
                     ass: Path | None, preview: bool) -> None:
    filtergraph = build_render_filter(fmt, layout, ass.name if ass else None,
                                      rcfg["preview_height"] if preview else None,
                                      fontsdir_tuong_doi(ass.parent) if ass else None)
    cmd = ["ffmpeg", "-y", "-ss", str(c["start"]), "-to", str(c["end"]), "-i", str(job.video),
           "-filter_complex", filtergraph, "-map", "[v]", "-map", "0:a?"]
    if preview:
        cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28"]
    else:
        cmd += ["-c:v", "libx264", "-preset", rcfg["preset"], "-crf", str(rcfg["crf"])]
    cmd += ["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart", str(out)]
    run_cmd(cmd, cwd=ass.parent if ass else None)


def _concat(files: list[Path], out: Path) -> None:
    """Các clip cùng định dạng có cùng thông số mã hóa nên ghép bằng -c copy."""
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{f.name}'\n" for f in files), encoding="utf-8")
    run_cmd(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
             "-movflags", "+faststart", str(out)])
    lst.unlink()
