"""Tải video YouTube vào `data/input/` bằng yt-dlp (mã nguồn mở, giấy phép Unlicense).

Phần quyết định là hàm thuần có test: link hợp lệ, đoạn cắt, giới hạn, tùy chọn yt-dlp, tên
file, bản ghi nguồn, dịch lỗi. Phần gọi mạng mỏng và nhận `ydl_factory` để test không cần mạng.

**Chỉ nhận link YouTube** (quyết định 2026-09-17): yt-dlp có extractor "generic" tải được URL
bất kỳ. Nếu Studio chuyển thẳng mọi URL cho yt-dlp, ai gửi được request tới Studio cũng khiến
máy tải từ địa chỉ tùy ý, kể cả mạng nội bộ. Link được chuẩn hóa về `watch?v=<id>` trước khi
đưa cho yt-dlp, nên tham số lạ (`list=`, theo dõi…) bị bỏ.

Bản quyền: điều khoản YouTube hạn chế việc tải video. Chỉ tải video bạn có quyền sử dụng;
giấy phép của video được ghi vào `<tên>.source.json` và cảnh báo nếu không phải Creative Commons.
"""
from __future__ import annotations

import re
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..config import DownloadSettings, Settings
from ..utils.files import write_json
from ..utils.logger import log
from ..utils.timestamps import format_ts, parse_ts
from ..workspace import slug
from .ffmpeg import require_binary, which

YOUTUBE_HOSTS = frozenset({
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
    "youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com",
})
# Thứ tự ưu tiên khi js_runtime=auto: deno là mặc định của yt-dlp
JS_RUNTIMES = ("deno", "node", "bun")
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
TEN_TOI_DA = 40      # số ký tự tối đa của phần tiêu đề trong tên file tải về
DUNG_SAI_GIAY = 1.0  # cho phép --to vượt thời lượng báo về một chút (làm tròn phía YouTube)

Progress = Callable[[float | None, str], None]


class DownloadError(RuntimeError):
    """Không tải được video — thông báo đã là câu tiếng Việt nói rõ phải làm gì."""


@dataclass(frozen=True)
class Section:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    source: dict[str, Any]
    skipped: bool


# ------------------------------------------------------------------ hàm thuần
def parse_youtube_url(url: str) -> str:
    """Link YouTube → mã video 11 ký tự. Link không hợp lệ thì báo rõ vì sao."""
    raw = (url or "").strip()
    if not raw:
        raise DownloadError("Chưa nhập link YouTube.")
    if "://" not in raw:
        raw = "https://" + raw  # người dùng hay dán "youtu.be/abc…" không có https://
    parsed = urlparse(raw)
    try:
        port = parsed.port
    except ValueError:
        port = -1
    host = (parsed.hostname or "").casefold()
    if (parsed.scheme.casefold() not in ("http", "https") or host not in YOUTUBE_HOSTS
            or parsed.username or parsed.password or port not in (None, 80, 443)):
        raise DownloadError(f"Chỉ hỗ trợ link YouTube (youtube.com, youtu.be), không nhận: {url}")

    parts = [p for p in parsed.path.split("/") if p]
    query = parse_qs(parsed.query)
    if host == "youtu.be":
        video_id = parts[0] if parts else ""
    elif parts[:1] == ["watch"]:
        video_id = (query.get("v") or [""])[0]
    elif len(parts) >= 2 and parts[0] in ("shorts", "live", "embed", "v"):
        video_id = parts[1]
    else:
        video_id = ""

    if not _VIDEO_ID.match(video_id):
        if "list" in query or parts[:1] == ["playlist"]:
            raise DownloadError("Đây là link playlist. Mở một video trong playlist rồi copy link "
                                "của riêng video đó.")
        raise DownloadError(f"Không tìm thấy mã video trong link: {url}")
    return video_id


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def is_youtube_link(text: str) -> bool:
    """Chuỗi người dùng đưa vào trông như một link (không phải đường dẫn file)?

    Chỉ để phân loại đầu vào của `automeme run`; link có hợp lệ hay không do
    `parse_youtube_url` quyết định và báo lỗi rõ ràng.
    """
    t = (text or "").strip().casefold()
    return t.startswith(("http://", "https://")) or bool(
        re.match(r"^(www\.|m\.|music\.)?(youtube\.com|youtu\.be)/", t))


def format_download_summary(result: DownloadResult) -> str:
    """Vài dòng in ra sau khi tải xong."""
    src = result.source
    section = src.get("section")
    doan = ("cả video" if not section
            else f"{format_ts(section['start'])} → {format_ts(section['end'])}")
    dong = [
        ("Đã có sẵn: " if result.skipped else "Đã tải: ") + str(result.path),
        f"  Tiêu đề:   {src.get('title')}",
        f"  Kênh:      {src.get('channel') or 'không rõ'}",
        f"  Đoạn:      {doan}",
        f"  Giấy phép: {src.get('license') or 'không ghi'}",
    ]
    if not src.get("creative_commons"):
        dong.append("  Lưu ý: video không ghi giấy phép Creative Commons — chỉ dùng nếu bạn có "
                    "quyền với nội dung này.")
    dong.append(f'Tiếp theo: automeme run "{result.path}"')
    return "\n".join(dong)


def parse_section(start: str | None, end: str | None, *,
                  video_duration: float | None) -> Section | None:
    """`--from/--to` → đoạn cần tải. Không nhập gì thì tải cả video (None)."""
    start = (start or "").strip()
    end = (end or "").strip()
    if not start and not end:
        return None
    try:
        s = parse_ts(start) if start else 0.0
        e = parse_ts(end) if end else video_duration
    except ValueError as exc:
        raise DownloadError(str(exc)) from None
    if e is None:
        raise DownloadError("Không biết thời lượng video — hãy nhập cả thời điểm kết thúc (--to).")
    if video_duration is not None and e > video_duration + DUNG_SAI_GIAY:
        raise DownloadError(f"Thời điểm kết thúc {format_ts(e)} vượt quá thời lượng video "
                            f"({format_ts(video_duration)}).")
    if video_duration is not None:
        e = min(e, video_duration)
    if e <= s:
        raise DownloadError(f"Đoạn cắt không hợp lệ: kết thúc ({format_ts(e)}) phải sau bắt đầu "
                            f"({format_ts(s)}).")
    return Section(start=round(s, 3), end=round(e, 3))


def check_limits(info: dict[str, Any], section: Section | None, cfg: DownloadSettings) -> None:
    """Chặn trước khi tải: livestream, video/đoạn quá dài so với `download.max_duration`."""
    if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming", "post_live"):
        raise DownloadError("Video đang phát trực tiếp hoặc chưa công chiếu — chưa hỗ trợ tải.")
    duration = info.get("duration")
    if section is not None:
        if section.duration > cfg.max_duration:
            raise DownloadError(
                f"Đoạn cắt dài {format_ts(section.duration)}, vượt giới hạn "
                f"{format_ts(cfg.max_duration)} (download.max_duration). Chọn đoạn ngắn hơn.")
        return
    if duration and duration > cfg.max_duration:
        raise DownloadError(
            f"Video dài {format_ts(duration)}, vượt giới hạn {format_ts(cfg.max_duration)}. "
            f"Chọn một đoạn bằng --from/--to (ví dụ --from 1:20 --to 2:40), hoặc tăng "
            f"download.max_duration trong configs/.")


def pick_js_runtime(preference: str, finder: Callable[[str], str | None] = which
                    ) -> tuple[str, str] | None:
    """(tên, đường dẫn) của JS runtime sẽ dùng, hoặc None nếu không có/tắt."""
    if preference == "none":
        return None
    candidates = JS_RUNTIMES if preference == "auto" else (preference,)
    for name in candidates:
        path = finder(name)
        if path:
            return name, path
    return None


def build_ydl_options(*, out_dir: Path, cfg: DownloadSettings, section: Section | None,
                      js_runtime: tuple[str, str] | None, ffmpeg_location: str | None,
                      progress_hook: Callable[[dict[str, Any]], None] | None = None,
                      logger: Any = None) -> dict[str, Any]:
    """Tùy chọn cho `yt_dlp.YoutubeDL`.

    Ưu tiên H.264 + AAC trong MP4: xem được ngay trong Studio và FFmpeg giải mã nhanh; YouTube
    thường có H.264 tới 1080p. Không có thì mới lấy codec khác.
    """
    h = cfg.max_height
    options: dict[str, Any] = {
        "format": f"bv*[height<={h}]+ba/b[height<={h}]/bv*+ba/b",
        "format_sort": ["vcodec:h264", "acodec:aac"],
        "merge_output_format": "mp4",
        "outtmpl": {"default": str(out_dir / "%(id)s.%(ext)s")},
        "noplaylist": True,
        "max_filesize": cfg.max_filesize_mb * 1024 * 1024,
        "quiet": True,
        "noprogress": True,
        "retries": 3,
        "fragment_retries": 3,
        "overwrites": True,
        "warn_when_outdated": True,
    }
    if ffmpeg_location:
        options["ffmpeg_location"] = ffmpeg_location
    if js_runtime:
        name, path = js_runtime
        options["js_runtimes"] = {name: {"path": path}}
    if progress_hook:
        options["progress_hooks"] = [progress_hook]
    if logger is not None:
        options["logger"] = logger
    if section is not None:
        khoang = [{"start_time": section.start, "end_time": section.end}]
        options["download_ranges"] = lambda _info, _ydl: khoang
        options["force_keyframes_at_cuts"] = True  # cắt đúng khung hình, không lệch theo keyframe
    return options


def output_name(info: dict[str, Any], section: Section | None) -> str:
    """`<tieu-de>-<id>.mp4`, thêm `-<từ>s-<đến>s` khi chỉ tải một đoạn.

    Tiêu đề được rút gọn tới ranh giới chữ (tối đa `TEN_TOI_DA` ký tự) và gộp gạch nối liên tiếp:
    "Big Buck Bunny 60fps 4K - Official…" → "big-buck-bunny-60fps-4k-official".
    """
    ten = re.sub(r"-{2,}", "-", slug(str(info.get("title") or "youtube"), max_len=200))
    if len(ten) > TEN_TOI_DA:
        cat = ten[:TEN_TOI_DA + 1]
        ten = cat.rsplit("-", 1)[0] if "-" in cat else cat[:TEN_TOI_DA]
    ten = ten.strip("-._") or "youtube"
    video_id = str(info.get("id") or "")
    if not _VIDEO_ID.match(video_id):
        raise DownloadError("yt-dlp trả về mã video không hợp lệ.")
    doan = "" if section is None else f"-{int(section.start)}s-{int(section.end)}s"
    return f"{ten}-{video_id}{doan}.mp4"


def is_creative_commons(license_text: str | None) -> bool:
    return "creative commons" in (license_text or "").casefold()


def source_record(info: dict[str, Any], section: Section | None, *, tool_version: str,
                  downloaded_at: datetime) -> dict[str, Any]:
    """Nội dung `<tên>.source.json`: đủ để ghi nguồn và tự kiểm tra quyền sử dụng về sau."""
    license_text = info.get("license")
    return {
        "source": "youtube",
        "url": canonical_url(str(info.get("id"))),
        "id": info.get("id"),
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "channel_url": info.get("channel_url") or info.get("uploader_url"),
        "upload_date": info.get("upload_date"),
        "duration": info.get("duration"),
        "license": license_text,
        "creative_commons": is_creative_commons(license_text),
        "section": None if section is None else {"start": section.start, "end": section.end},
        "downloaded_at": downloaded_at.isoformat(timespec="seconds"),
        "tool": f"yt-dlp {tool_version}",
    }


def progress_message(event: dict[str, Any]) -> tuple[float | None, str] | None:
    """Sự kiện progress của yt-dlp → (phần trăm hoặc None, câu mô tả). None = bỏ qua."""
    status = event.get("status")
    info = event.get("info_dict") or {}
    phan = "âm thanh" if info.get("vcodec") == "none" else "hình"
    if status == "downloading":
        total = event.get("total_bytes") or event.get("total_bytes_estimate")
        done = event.get("downloaded_bytes")
        if total and done is not None:
            percent = max(0.0, min(100.0, done * 100 / total))
            return percent, f"Đang tải {phan}: {percent:.0f}%"
        return None, f"Đang tải {phan}…"
    if status == "finished":
        return 100.0, f"Đã tải xong {phan}, đang xử lý"
    return None


CAP_NHAT = "Thử cập nhật: python -m pip install -U yt-dlp"

# (các cụm từ trong lỗi yt-dlp, câu hướng dẫn) — xét theo thứ tự, khớp cụm đầu tiên
_LOI_DA_BIET: tuple[tuple[tuple[str, ...], str], ...] = (
    (("private video",), "Video ở chế độ riêng tư — không tải được."),
    (("confirm your age", "age-restricted", "inappropriate for some users"),
     "Video bị giới hạn độ tuổi, cần đăng nhập — bản này chưa hỗ trợ."),
    (("not a bot",), f"YouTube tạm chặn vì nghi là bot. Đợi một lúc rồi thử lại. {CAP_NHAT}"),
    (("members-only", "join this channel"), "Video chỉ dành cho hội viên kênh — không tải được."),
    (("video unavailable", "has been removed", "not available in your country"),
     "Video không tồn tại, đã bị gỡ hoặc bị chặn ở khu vực của bạn."),
    (("live event", "premieres in"),
     "Video đang phát trực tiếp hoặc chưa công chiếu — chưa hỗ trợ tải."),
    (("larger than max-filesize", "max_filesize"),
     "Video vượt giới hạn dung lượng (download.max_filesize_mb). Chọn đoạn ngắn hơn."),
    (("ffmpeg not found", "ffmpeg is not installed"),
     "yt-dlp cần FFmpeg để ghép hình và tiếng: winget install Gyan.FFmpeg"),
)


def explain_download_error(message: str) -> str:
    """Đổi lỗi của yt-dlp thành câu tiếng Việt nói rõ phải làm gì."""
    thap = message.casefold()
    for cum_tu, huong_dan in _LOI_DA_BIET:
        if any(c in thap for c in cum_tu):
            return huong_dan
    if any(c in thap for c in ("getaddrinfo", "timed out", "connection", "network is unreachable")):
        return f"Lỗi mạng khi tải video. Kiểm tra kết nối rồi thử lại. Chi tiết: {message}"
    if any(c in thap for c in ("http error 403", "requested format is not available", "signature")):
        return f"YouTube vừa thay đổi cách phát video. {CAP_NHAT}. Chi tiết: {message}"
    return f"Không tải được video: {message}. {CAP_NHAT}"


# ------------------------------------------------------------------ gọi yt-dlp (mỏng)
class _YdlLogger:
    """Đưa log của yt-dlp vào log của automeme (file log mức DEBUG)."""

    def debug(self, msg: str) -> None:
        log.debug("yt-dlp: %s", msg)

    def info(self, msg: str) -> None:
        log.debug("yt-dlp: %s", msg)

    def warning(self, msg: str) -> None:
        log.warning("yt-dlp: %s", msg)

    def error(self, msg: str) -> None:
        log.debug("yt-dlp lỗi: %s", msg)  # lỗi được ném lên và dịch ở nơi gọi


def _default_factory(options: dict[str, Any]) -> Any:
    try:
        import yt_dlp
    except ImportError as exc:
        raise DownloadError("Chưa cài yt-dlp: python -m pip install -e .") from exc
    return yt_dlp.YoutubeDL(options)


def _tool_version() -> str:
    try:
        from importlib.metadata import version
        return version("yt-dlp")
    except Exception:  # không đọc được phiên bản thì vẫn tải bình thường
        return "?"


def download_youtube(url: str, settings: Settings, *, start: str | None = None,
                     end: str | None = None, force: bool = False,
                     progress: Progress | None = None,
                     ydl_factory: Callable[[dict[str, Any]], Any] | None = None,
                     now: Callable[[], datetime] | None = None) -> DownloadResult:
    """Tải một video (hoặc một đoạn) vào `data/input/`. Đã có file thì bỏ qua (trừ `force`)."""
    video_id = parse_youtube_url(url)
    link = canonical_url(video_id)
    cfg = settings.download
    factory = ydl_factory or _default_factory
    ffmpeg = require_binary("ffmpeg")
    runtime = pick_js_runtime(cfg.js_runtime)
    if runtime is None and cfg.js_runtime != "none":
        log.warning("Không thấy JS runtime (deno/node/bun) — YouTube có thể thiếu định dạng. "
                    "Cài Deno: winget install DenoLand.Deno")

    data_dir = settings.paths.data_dir
    input_dir = data_dir / "input"
    tmp_dir = data_dir / "temp" / f"youtube-{video_id}-{uuid.uuid4().hex[:8]}"
    input_dir.mkdir(parents=True, exist_ok=True)

    def bao(percent: float | None, message: str) -> None:
        if progress is not None:
            progress(percent, message)

    bao(None, "Đang đọc thông tin video")
    log.info("Đọc thông tin video YouTube %s…", video_id)
    options = build_ydl_options(out_dir=tmp_dir, cfg=cfg, section=None, js_runtime=runtime,
                                ffmpeg_location=ffmpeg, logger=_YdlLogger())
    try:
        with factory(options) as ydl:
            info = ydl.sanitize_info(ydl.extract_info(link, download=False))
    except DownloadError:
        raise
    except Exception as exc:
        raise DownloadError(explain_download_error(str(exc))) from exc

    section = parse_section(start, end, video_duration=info.get("duration"))
    check_limits(info, section, cfg)
    target = input_dir / output_name(info, section)
    sidecar = target.with_name(target.stem + ".source.json")
    record = source_record(info, section, tool_version=_tool_version(),
                           downloaded_at=(now or (lambda: datetime.now(timezone.utc)))())
    if not record["creative_commons"]:
        log.warning("Video \"%s\" không ghi giấy phép Creative Commons (%s). Chỉ dùng nếu bạn có "
                    "quyền với nội dung này.", info.get("title"), record["license"] or "không rõ")

    if target.exists() and not force:
        log.info("Đã có %s, bỏ qua tải. Thêm --force để tải lại.", target.name)
        if not sidecar.exists():
            write_json(sidecar, record)
        bao(100.0, f"Đã có sẵn {target.name}")
        return DownloadResult(path=target, source=record, skipped=True)

    doan = ("cả video" if section is None
            else f"đoạn {format_ts(section.start)}–{format_ts(section.end)}")
    log.info("Tải %s của \"%s\" (%s)…", doan, info.get("title"),
             format_ts(info.get("duration") or 0))

    def hook(event: dict[str, Any]) -> None:
        tin = progress_message(event)
        if tin is not None:
            bao(*tin)

    options = build_ydl_options(out_dir=tmp_dir, cfg=cfg, section=section, js_runtime=runtime,
                                ffmpeg_location=ffmpeg, progress_hook=hook, logger=_YdlLogger())
    # Tải theo đoạn thì yt-dlp cắt bằng FFmpeg và không báo phần trăm — báo trước một câu để
    # giao diện không đứng mãi ở "Đang đọc thông tin video".
    bao(None, f"Đang tải {doan} — có thể mất một lúc")
    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            with factory(options) as ydl:
                ydl.download([link])
        except Exception as exc:
            raise DownloadError(explain_download_error(str(exc))) from exc

        produced = sorted(tmp_dir.glob(f"{video_id}*.mp4"))
        if not produced:
            raise DownloadError("yt-dlp chạy xong nhưng không thấy file MP4 — xem "
                                "data/logs/automeme.log.")
        bao(None, "Đang lưu video")
        shutil.move(str(produced[0]), target.with_name(target.name + ".part"))
        target.with_name(target.name + ".part").replace(target)
        write_json(sidecar, record)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        target.with_name(target.name + ".part").unlink(missing_ok=True)

    log.info("Đã tải: %s", target)
    bao(100.0, f"Đã tải xong {target.name}")
    return DownloadResult(path=target, source=record, skipped=False)
