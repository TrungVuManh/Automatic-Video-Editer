"""Bước 4b — Duyệt clip trên terminal (tuần 4 sẽ thay bằng trang HTML).

Mỗi quyết định được ghi vào feedback/examples.jsonl để lần sau đưa vào prompt.
"""
from __future__ import annotations

import shutil
import subprocess

from .common import FEEDBACK_FILE, Job, append_jsonl, fmt_time, log, read_json, write_json


def review(job: Job) -> None:
    clips = read_json(job.clips)
    player = shutil.which("ffplay")
    print(f"\n{len(clips)} clip cần duyệt. Lệnh: [y] giữ  [n] loại  [p] xem thử  [s] để sau  [q] thoát\n")

    for c in clips:
        if c.get("approved") is not None:
            continue
        print(f"— {c['id']}  {fmt_time(c['start'])} → {fmt_time(c['end'])}  "
              f"({c['end'] - c['start']:.0f}s)  [{c['loai']}]  điểm {c['diem']}")
        print(f"  Tiêu đề: {c['tieu_de']}\n  Hook:    {c['hook']}\n  Lý do:   {c['ly_do']}")

        while True:
            ans = input("  > ").strip().lower()
            if ans == "p":
                if player:
                    subprocess.run([player, "-autoexit", "-ss", str(c["start"]),
                                    "-t", str(c["end"] - c["start"]), "-loglevel", "quiet", str(job.video)])
                else:
                    print("  (Cần ffplay — đi kèm bản FFmpeg đầy đủ)")
                continue
            if ans in {"y", "n", "s", "q"}:
                break

        if ans == "q":
            break
        if ans == "s":
            continue
        c["approved"] = ans == "y"
        note = input("  Ghi chú (Enter để bỏ qua): ").strip()
        append_jsonl(FEEDBACK_FILE, {
            "kind": "clip", "streamer": job.streamer, "job": job.name,
            "approved": c["approved"], "loai": c["loai"], "tieu_de": c["tieu_de"],
            "ly_do": c["ly_do"], "note": note,
        })
        write_json(job.clips, clips)  # lưu ngay sau mỗi quyết định

    kept = sum(1 for c in clips if c.get("approved"))
    log.info("Đã duyệt: giữ %d/%d clip.", kept, len(clips))
