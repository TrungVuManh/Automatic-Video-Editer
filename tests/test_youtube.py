from datetime import datetime, timezone
from pathlib import Path

import pytest

import automeme.media.youtube as yt
from automeme.config import load_settings
from automeme.media.youtube import (
    DownloadError,
    Section,
    build_ydl_options,
    canonical_url,
    check_limits,
    download_youtube,
    explain_download_error,
    output_name,
    parse_section,
    parse_youtube_url,
    pick_js_runtime,
    progress_message,
    source_record,
)
from automeme.utils.files import read_json

ID = "aqz-KE-bpKQ"


# ------------------------------------------------------------------ link
@pytest.mark.parametrize("url", [
    f"https://www.youtube.com/watch?v={ID}",
    f"https://youtube.com/watch?v={ID}&t=30s",
    f"https://www.youtube.com/watch?v={ID}&list=PL123&index=2",  # video trong playlist → lấy video
    f"https://m.youtube.com/watch?v={ID}",
    f"https://music.youtube.com/watch?v={ID}",
    f"https://youtu.be/{ID}?si=abc",
    f"https://www.youtube.com/shorts/{ID}",
    f"https://www.youtube.com/live/{ID}",
    f"https://www.youtube-nocookie.com/embed/{ID}",
    f"youtu.be/{ID}",                                            # dán thiếu https://
    f"  https://www.youtube.com/watch?v={ID}  ",
])
def test_nhan_moi_dang_link_youtube(url):
    assert parse_youtube_url(url) == ID


@pytest.mark.parametrize("url, loi", [
    ("", "Chưa nhập"),
    (f"https://vimeo.com/{ID}", "Chỉ hỗ trợ link YouTube"),
    (f"https://youtube.com.evil.com/watch?v={ID}", "Chỉ hỗ trợ link YouTube"),
    (f"https://evil.com/youtube.com/watch?v={ID}", "Chỉ hỗ trợ link YouTube"),
    (f"https://www.youtube.com@evil.com/watch?v={ID}", "Chỉ hỗ trợ link YouTube"),
    (f"https://user@www.youtube.com/watch?v={ID}", "Chỉ hỗ trợ link YouTube"),
    (f"https://www.youtube.com:8080/watch?v={ID}", "Chỉ hỗ trợ link YouTube"),
    (f"ftp://www.youtube.com/watch?v={ID}", "Chỉ hỗ trợ link YouTube"),
    ("http://127.0.0.1/watch?v=aqz-KE-bpKQ", "Chỉ hỗ trợ link YouTube"),
    ("https://www.youtube.com/playlist?list=PL123", "playlist"),
    ("https://www.youtube.com/watch?v=ngan", "Không tìm thấy mã video"),
    ("https://www.youtube.com/@kenhabc", "Không tìm thấy mã video"),
])
def test_tu_choi_link_khong_phai_mot_video_youtube(url, loi):
    with pytest.raises(DownloadError, match=loi):
        parse_youtube_url(url)


def test_link_chuan_hoa_bo_tham_so_la():
    assert canonical_url(ID) == f"https://www.youtube.com/watch?v={ID}"


# ------------------------------------------------------------------ đoạn cắt + giới hạn
def test_khong_nhap_doan_thi_tai_ca_video():
    assert parse_section(None, "", video_duration=100) is None


@pytest.mark.parametrize("start, end, duration, mong_doi", [
    ("1:20", "2:40", 635, Section(80, 160)),
    ("30", None, 100, Section(30, 100)),       # thiếu --to → tới hết video
    (None, "0:45.5", 100, Section(0, 45.5)),   # thiếu --from → từ đầu
    ("90", "100.4", 100, Section(90, 100)),    # vượt thời lượng trong sai số → kẹp lại
])
def test_parse_section(start, end, duration, mong_doi):
    assert parse_section(start, end, video_duration=duration) == mong_doi


@pytest.mark.parametrize("start, end, duration, loi", [
    ("2:00", "1:00", 300, "phải sau bắt đầu"),
    ("0:10", "0:10", 300, "phải sau bắt đầu"),
    ("0:10", "6:00", 300, "vượt quá thời lượng"),
    ("abc", "1:00", 300, "không hợp lệ"),
    ("0:10", None, None, "thời điểm kết thúc"),
])
def test_parse_section_bao_loi(start, end, duration, loi):
    with pytest.raises(DownloadError, match=loi):
        parse_section(start, end, video_duration=duration)


@pytest.fixture
def settings(tmp_path):
    return load_settings(env={}, root=tmp_path)


def test_video_dai_phai_chon_doan(settings):
    with pytest.raises(DownloadError, match="--from/--to"):
        check_limits({"duration": 635}, None, settings.download)
    check_limits({"duration": 635}, Section(30, 90), settings.download)  # có đoạn thì được
    check_limits({"duration": 90}, None, settings.download)


def test_doan_qua_dai_bi_chan(settings):
    with pytest.raises(DownloadError, match="Đoạn cắt dài"):
        check_limits({"duration": 3600}, Section(0, 1200), settings.download)


@pytest.mark.parametrize("info", [{"is_live": True}, {"live_status": "is_upcoming"}])
def test_livestream_bi_chan(info, settings):
    with pytest.raises(DownloadError, match="trực tiếp"):
        check_limits(info, None, settings.download)


# ------------------------------------------------------------------ JS runtime + tùy chọn
def test_chon_js_runtime():
    co = {"node": "C:/node.exe", "bun": "C:/bun.exe"}
    assert pick_js_runtime("auto", co.get) == ("node", "C:/node.exe")  # deno vắng → node
    assert pick_js_runtime("bun", co.get) == ("bun", "C:/bun.exe")
    assert pick_js_runtime("deno", co.get) is None
    assert pick_js_runtime("none", co.get) is None


def test_tuy_chon_yt_dlp_ca_video(settings, tmp_path):
    opts = build_ydl_options(out_dir=tmp_path, cfg=settings.download, section=None,
                             js_runtime=("node", "C:/node.exe"), ffmpeg_location="C:/ffmpeg.exe")
    assert opts["noplaylist"] is True and opts["merge_output_format"] == "mp4"
    assert "height<=1080" in opts["format"]
    assert opts["format_sort"][0] == "vcodec:h264"
    assert opts["js_runtimes"] == {"node": {"path": "C:/node.exe"}}
    assert opts["ffmpeg_location"] == "C:/ffmpeg.exe"
    assert opts["max_filesize"] == 1024 * 1024 * 1024
    assert opts["outtmpl"]["default"] == str(tmp_path / "%(id)s.%(ext)s")
    assert "download_ranges" not in opts


def test_tuy_chon_yt_dlp_mot_doan(settings, tmp_path):
    opts = build_ydl_options(out_dir=tmp_path, cfg=settings.download, section=Section(80, 160),
                             js_runtime=None, ffmpeg_location=None)
    assert list(opts["download_ranges"]({}, None)) == [{"start_time": 80, "end_time": 160}]
    assert opts["force_keyframes_at_cuts"] is True
    assert "js_runtimes" not in opts


# ------------------------------------------------------------------ tên file, nguồn, tiến độ
def test_ten_file():
    info = {"id": ID, "title": "Big Buck Bunny: Phim Ngắn!"}
    assert output_name(info, None) == f"big-buck-bunny-phim-ngan-{ID}.mp4"
    assert output_name(info, Section(30.5, 60)) == f"big-buck-bunny-phim-ngan-{ID}-30s-60s.mp4"
    # tiêu đề thật khi nghiệm thu: gộp "---" và cắt ở ranh giới chữ, không cắt giữa từ
    dai = {"id": ID, "title": "Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film"}
    assert output_name(dai, None) == f"big-buck-bunny-60fps-4k-official-blender-{ID}.mp4"
    assert output_name({"id": ID, "title": "!!!"}, None) == f"video-{ID}.mp4"
    with pytest.raises(DownloadError):
        output_name({"id": "../../x", "title": "t"}, None)


def test_ban_ghi_nguon():
    info = {"id": ID, "title": "BBB", "uploader": "Blender", "duration": 635,
            "license": "Creative Commons Attribution license (reuse allowed)"}
    record = source_record(info, Section(30, 60), tool_version="2026.8.19",
                           downloaded_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc))
    assert record["url"] == canonical_url(ID) and record["channel"] == "Blender"
    assert record["creative_commons"] is True
    assert record["section"] == {"start": 30, "end": 60}
    assert record["downloaded_at"] == "2026-09-17T12:00:00+00:00"
    assert source_record({"id": ID}, None, tool_version="x",
                         downloaded_at=datetime.now(timezone.utc))["creative_commons"] is False


def test_thong_bao_tien_do():
    video = {"vcodec": "avc1"}
    assert progress_message({"status": "downloading", "downloaded_bytes": 50,
                             "total_bytes": 200, "info_dict": video}) == (25.0,
                                                                         "Đang tải hình: 25%")
    assert progress_message({"status": "downloading", "downloaded_bytes": 10,
                             "total_bytes_estimate": 20,
                             "info_dict": {"vcodec": "none"}})[1] == "Đang tải âm thanh: 50%"
    khong_ro_tong = progress_message({"status": "downloading", "info_dict": video})
    assert khong_ro_tong == (None, "Đang tải hình…")
    assert progress_message({"status": "finished", "info_dict": video})[0] == 100.0
    assert progress_message({"status": "error"}) is None


@pytest.mark.parametrize("loi, mong_doi", [
    ("ERROR: [youtube] x: Private video. Sign in", "riêng tư"),
    ("Sign in to confirm your age", "giới hạn độ tuổi"),
    ("Sign in to confirm you're not a bot", "nghi là bot"),
    ("Video unavailable. This video has been removed", "không tồn tại"),
    ("File is larger than max-filesize", "dung lượng"),
    ("HTTP Error 403: Forbidden", "pip install -U yt-dlp"),
    ("<urlopen error [Errno 11001] getaddrinfo failed>", "Lỗi mạng"),
    ("lỗi chưa gặp bao giờ", "Không tải được video"),
])
def test_dich_loi_yt_dlp(loi, mong_doi):
    assert mong_doi in explain_download_error(loi)


# ------------------------------------------------------------------ tải (yt-dlp giả)
class YdlGia:
    """Giả lập yt_dlp.YoutubeDL: ghi nhận tùy chọn, tạo file MP4 trong thư mục tạm."""

    def __init__(self, info, calls, loi_khi_tai=None):
        self.info, self.calls, self.loi_khi_tai = info, calls, loi_khi_tai

    def __call__(self, options):
        self.options = options
        self.calls.append(("init", options))
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        self.calls.append(("extract", url))
        return dict(self.info)

    def sanitize_info(self, info):
        return info

    def download(self, urls):
        self.calls.append(("download", urls))
        if self.loi_khi_tai:
            raise RuntimeError(self.loi_khi_tai)
        out = Path(self.options["outtmpl"]["default"].replace("%(id)s", self.info["id"])
                   .replace("%(ext)s", "mp4"))
        out.write_bytes(b"MP4 gia")
        for hook in self.options.get("progress_hooks", []):
            hook({"status": "downloading", "downloaded_bytes": 5, "total_bytes": 10,
                  "info_dict": {"vcodec": "avc1"}})
            hook({"status": "finished", "info_dict": {"vcodec": "avc1"}})


INFO = {"id": ID, "title": "Big Buck Bunny", "duration": 635, "channel": "Blender",
        "license": "Creative Commons Attribution license (reuse allowed)"}


@pytest.fixture(autouse=True)
def _khong_can_ffmpeg_that(monkeypatch):
    monkeypatch.setattr(yt, "require_binary", lambda name: name)
    monkeypatch.setattr(yt, "pick_js_runtime", lambda pref: ("node", "node"))


def test_tai_mot_doan_ghi_video_va_nguon(settings):
    calls, tien_do = [], []
    fake = YdlGia(INFO, calls)
    kq = download_youtube(f"https://youtu.be/{ID}?si=x", settings, start="0:30", end="1:00",
                          progress=lambda p, m: tien_do.append((p, m)), ydl_factory=fake)
    assert not kq.skipped
    assert kq.path == settings.paths.data_dir / "input" / f"big-buck-bunny-{ID}-30s-60s.mp4"
    assert kq.path.read_bytes() == b"MP4 gia"
    nguon = read_json(kq.path.with_name(kq.path.stem + ".source.json"))
    assert nguon["section"] == {"start": 30, "end": 60} and nguon["creative_commons"] is True
    # link đưa cho yt-dlp đã chuẩn hóa, và chỉ lần tải mới có download_ranges
    assert ("extract", canonical_url(ID)) in calls and ("download", [canonical_url(ID)]) in calls
    inits = [opts for kind, opts in calls if kind == "init"]
    assert "download_ranges" not in inits[0] and "download_ranges" in inits[1]
    assert (50.0, "Đang tải hình: 50%") in tien_do and tien_do[-1][0] == 100.0
    # thư mục tạm đã dọn, không sót file .part
    assert not list((settings.paths.data_dir / "temp").glob("youtube-*"))
    assert not list((settings.paths.data_dir / "input").glob("*.part"))


def test_da_co_file_thi_bo_qua_tru_khi_force(settings):
    calls = []
    fake = YdlGia(INFO, calls)
    download_youtube(ID_URL := f"https://youtu.be/{ID}", settings, start="0:30", end="1:00",
                     ydl_factory=fake)
    calls.clear()
    kq = download_youtube(ID_URL, settings, start="0:30", end="1:00", ydl_factory=fake)
    assert kq.skipped and not any(kind == "download" for kind, _ in calls)
    kq = download_youtube(ID_URL, settings, start="0:30", end="1:00", force=True,
                          ydl_factory=fake)
    assert not kq.skipped and any(kind == "download" for kind, _ in calls)


def test_video_dai_khong_chon_doan_thi_dung_truoc_khi_tai(settings):
    calls = []
    with pytest.raises(DownloadError, match="--from/--to"):
        download_youtube(f"https://youtu.be/{ID}", settings, ydl_factory=YdlGia(INFO, calls))
    assert not any(kind == "download" for kind, _ in calls)


def test_loi_khi_tai_duoc_dich_va_don_sach(settings):
    fake = YdlGia(INFO, [], loi_khi_tai="HTTP Error 403: Forbidden")
    with pytest.raises(DownloadError, match="pip install -U yt-dlp"):
        download_youtube(f"https://youtu.be/{ID}", settings, start="0", end="30", ydl_factory=fake)
    assert not list((settings.paths.data_dir / "input").glob("*.mp4"))
    assert not list((settings.paths.data_dir / "temp").glob("youtube-*"))


def test_link_sai_khong_goi_yt_dlp(settings):
    calls = []
    with pytest.raises(DownloadError):
        download_youtube("https://evil.com/x", settings, ydl_factory=YdlGia(INFO, calls))
    assert calls == []


def test_canh_bao_khi_khong_phai_creative_commons(settings, caplog):
    info = {**INFO, "license": None}
    with caplog.at_level("WARNING", logger="automeme"):
        download_youtube(f"https://youtu.be/{ID}", settings, start="0", end="30",
                         ydl_factory=YdlGia(info, []))
    assert any("Creative Commons" in r.getMessage() for r in caplog.records)
