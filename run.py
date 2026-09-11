"""Điểm vào của pipeline.

Ví dụ:
  python run.py all --job 2026-09-10_vod01 --streamer streamer_example --platform youtube --url URL
  python run.py all --job test01 --streamer streamer_example --platform youtube --video clip.mp4
  python run.py review  --job 2026-09-10_vod01
  python run.py render  --job 2026-09-10_vod01 --format ca-hai [--preview]
  python run.py doctor                           # kiểm tra môi trường
  python run.py inspect --job 2026-09-10_vod01   # bảng điểm tín hiệu tại mỗi đỉnh
"""
from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from pipeline.common import Job, add_file_log, load_settings, load_streamer, log, setup_logging

STEPS = ["fetch", "preprocess", "candidates", "select"]


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(description="Tự động cắt highlight stream game bằng Claude")
    ap.add_argument("step", choices=["all", *STEPS, "review", "render", "inspect", "doctor"])
    ap.add_argument("--job", help="tên job, ví dụ 2026-09-10_vod01 (mọi lệnh trừ doctor)")
    ap.add_argument("--streamer", help="tên preset trong config/ (bắt buộc khi tạo job mới)")
    ap.add_argument("--platform", choices=["youtube", "twitch"])
    ap.add_argument("--url", help="link VOD")
    ap.add_argument("--video", help="dùng file video có sẵn thay vì tải")
    ap.add_argument("--chat", help="dùng file chat có sẵn thay vì tải")
    ap.add_argument("--preview", action="store_true", help="render bản xem nhanh 480p")
    ap.add_argument("--all-clips", action="store_true", help="render cả clip chưa duyệt")
    ap.add_argument("--format", dest="dinh_dang", choices=["ngang", "doc", "ca-hai"],
                    help="định dạng khi render (mặc định lấy từ settings.yaml → render.dinh_dang)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    setup_logging(args.verbose)

    if args.step == "doctor":
        from pipeline.diagnostics import check_environment, format_checks
        print(format_checks(check_environment()))
        return

    if not args.job:
        sys.exit("Thiếu --job.")
    job = _get_job(args)
    add_file_log(job)  # từ đây mọi log được ghi thêm vào jobs/<job>/pipeline.log
    settings = load_settings()
    streamer = load_streamer(job.streamer)

    # Import muộn: không cần cài WhisperX chỉ để chạy review/render
    if args.step in ("all", "fetch"):
        from pipeline.s1_fetch import fetch
        fetch(job)
    if args.step in ("all", "preprocess"):
        from pipeline.s2_preprocess import preprocess
        preprocess(job, settings)
    if args.step in ("all", "candidates"):
        from pipeline.s3_candidates import find_candidates
        find_candidates(job, settings, streamer)
    if args.step in ("all", "select"):
        from pipeline.s4_select import select_clips
        select_clips(job, settings, streamer)
    if args.step == "review":
        from pipeline.s4b_review import review
        review(job)
    if args.step == "render":
        from pipeline.s7_render import render
        render(job, settings, streamer, preview=args.preview, include_pending=args.all_clips,
               dinh_dang=args.dinh_dang)
    if args.step == "inspect":
        from pipeline.diagnostics import build_inspect_rows, format_inspect_table
        print(format_inspect_table(build_inspect_rows(job, settings, streamer)))

    if args.step == "all":
        log.info("Xong! Bước tiếp theo: python run.py review --job %s", job.name)


def _get_job(args) -> Job:
    try:
        job = Job.load(args.job)
    except FileNotFoundError:
        if not (args.streamer and args.platform and (args.url or args.video)):
            sys.exit("Job mới cần --streamer, --platform và --url (hoặc --video).")
        job = Job(name=args.job, streamer=args.streamer, platform=args.platform,
                  url=args.url, local_video=args.video, local_chat=args.chat)
        job.save()
        log.info("Tạo job mới: %s", job.dir)
    return job


if __name__ == "__main__":
    main()
