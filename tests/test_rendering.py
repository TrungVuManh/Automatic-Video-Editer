from pathlib import Path

import pytest

from automeme.config import load_settings
from automeme.media.ffmpeg import CommandError, run_cmd, which
from automeme.media.probe import probe
from automeme.pipeline import render_timeline
from automeme.rendering.filters import build_render_plan, input_cho_meme, vi_tri_overlay
from automeme.rendering.renderer import build_ffmpeg_cmd, render
from automeme.timeline.schema import MemeEvent, Timeline, save_timeline

CAN_FFMPEG = pytest.mark.skipif(not (which("ffmpeg") and which("ffprobe")), reason="cần FFmpeg")


def _event(**kw) -> MemeEvent:
    return MemeEvent(**{"id": "e1", "start": 1.0, "duration": 1.5, "asset": "x.png", **kw})


def _plan(events, assets, **kw):
    cfg = {"video_w": 1920, "video_h": 1080, "scale_default": 0.30,
           "position_default": "bottom-right", "margin_ratio": 0.03}
    return build_render_plan(events, assets, **{**cfg, **kw})


# ------------------------------------------------------------------ hàm thuần
def test_khong_co_su_kien_thi_khong_loc_gi():
    plan = _plan([], [])
    assert plan.input_args == [] and plan.filter_complex == "" and plan.out_label == ""


def test_filter_cho_mot_meme():
    plan = _plan([_event()], [Path("x.png")])
    assert plan.filter_complex == (
        "[1:v]scale=576:-2,setpts=PTS-STARTPTS+1.000/TB[m0];"
        "[0:v][m0]overlay=W-w-58:H-h-58:enable='between(t,1.000,2.500)':eof_action=pass[v]"
    )
    assert plan.out_label == "[v]"


def test_be_rong_meme_bang_30_phan_tram_khung_va_luon_chan():
    assert "scale=576:-2" in _plan([_event()], [Path("x.png")]).filter_complex        # 30% × 1920
    assert "scale=324:-2" in _plan([_event()], [Path("x.png")],
                                   video_w=1080, video_h=1920).filter_complex          # 30% × 1080
    # scale riêng của sự kiện thắng mặc định; 0.2 × 1005 = 201 → làm tròn xuống số chẵn
    assert "scale=200:-2" in _plan([_event(scale=0.2)], [Path("x.png")],
                                   video_w=1005).filter_complex


def test_noi_nhieu_meme_thanh_chuoi_overlay():
    events = [_event(id="e1", start=1), _event(id="e2", start=5, position="center")]
    fc = _plan(events, [Path("a.png"), Path("b.gif")]).filter_complex
    assert "[0:v][m0]overlay=" in fc and "[v0]" in fc
    assert "[v0][m1]overlay=(W-w)/2:(H-h)/2" in fc
    assert fc.rstrip().endswith("[v]")


@pytest.mark.parametrize("vi_tri, x, y", [
    ("top-left", "10", "10"),
    ("top-right", "W-w-10", "10"),
    ("bottom-left", "10", "H-h-10"),
    ("bottom-right", "W-w-10", "H-h-10"),
    ("center", "(W-w)/2", "(H-h)/2"),
])
def test_vi_tri_overlay(vi_tri, x, y):
    assert vi_tri_overlay(vi_tri, 10) == (x, y)


def test_vi_tri_la_khong_bao_loi():
    with pytest.raises(ValueError, match="Vị trí không hợp lệ"):
        vi_tri_overlay("giữa màn hình", 10)


def test_input_khac_nhau_theo_loai_meme():
    assert input_cho_meme(Path("a.png"), 1.5)[:2] == ["-loop", "1"]
    assert input_cho_meme(Path("a.JPG"), 1.5)[:2] == ["-loop", "1"]
    assert input_cho_meme(Path("a.gif"), 1.5)[:2] == ["-ignore_loop", "0"]   # GIF phải lặp
    assert input_cho_meme(Path("a.webm"), 1.5)[:2] == ["-stream_loop", "-1"]
    assert input_cho_meme(Path("a.png"), 1.5)[-4:] == ["-t", "1.500", "-i", "a.png"]


def test_so_su_kien_va_asset_phai_khop():
    with pytest.raises(ValueError, match="không khớp"):
        _plan([_event()], [])


def test_lenh_ffmpeg_giu_audio_goc_va_dung_cau_hinh():
    plan = _plan([_event()], [Path("x.png")])
    cmd = build_ffmpeg_cmd(Path("in.mp4"), Path("out.mp4"), plan,
                           video_codec="libx264", crf=18, preset="medium")
    assert cmd[cmd.index("-i") + 1] == "in.mp4"
    assert "-filter_complex" in cmd and cmd[cmd.index("-map") + 1] == "[v]"
    assert "0:a?" in cmd                       # video không có tiếng vẫn chạy được
    assert cmd[cmd.index("-c:a") + 1] == "copy"
    assert cmd[cmd.index("-crf") + 1] == "18"
    assert cmd[-1] == "out.mp4"


def test_lenh_ffmpeg_khi_khong_co_meme_nao():
    cmd = build_ffmpeg_cmd(Path("in.mp4"), Path("out.mp4"), _plan([], []),
                           video_codec="libx264", crf=18, preset="medium")
    assert "-filter_complex" not in cmd and cmd[cmd.index("-map") + 1] == "0:v"


def test_lenh_ffmpeg_encode_lai_audio_khi_can():
    cmd = build_ffmpeg_cmd(Path("in.mp4"), Path("out.mp4"), _plan([], []),
                           video_codec="libx264", crf=18, preset="medium", audio_codec="aac")
    assert cmd[cmd.index("-c:a") + 1] == "aac"


# ------------------------------------------------------------------ render thật
@pytest.fixture
def du_an(tmp_path):
    """Một dự án nhỏ: video 5 giây có tiếng, một PNG trong suốt, một GIF động."""
    (tmp_path / "assets" / "memes").mkdir(parents=True)
    video = tmp_path / "clip.mp4"
    run_cmd(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=5",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-shortest", str(video)])
    png = tmp_path / "assets" / "memes" / "meme.png"
    run_cmd(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "color=c=red@0.8:size=120x80,format=rgba",
             "-frames:v", "1", str(png)])
    gif = tmp_path / "assets" / "memes" / "meme.gif"
    run_cmd(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "testsrc2=size=100x100:rate=10:duration=1",
             str(gif)])
    return tmp_path, video


@CAN_FFMPEG
def test_render_that_chen_png_va_gif(du_an):
    tmp_path, video = du_an
    settings = load_settings(env={"OUTPUT_PRESET": "ultrafast"}, root=tmp_path)
    timeline = Timeline(video=video.name, events=[
        MemeEvent(id="e1", start=1.0, duration=1.5, asset="assets/memes/meme.png"),
        MemeEvent(id="e2", start=3.0, duration=1.0, asset="assets/memes/meme.gif",
                  position="top-left", scale=0.25),
    ])
    save_timeline(tmp_path / "tl.json", timeline)

    out, _ = render_timeline(video, settings, timeline_path=tmp_path / "tl.json")
    assert out.exists()
    goc, moi = probe(video), probe(out)
    assert moi.duration == pytest.approx(goc.duration, abs=0.2)   # không bị cắt ngắn
    assert (moi.width, moi.height) == (goc.width, goc.height)
    assert moi.has_audio                                          # giữ được tiếng gốc
    assert not list(out.parent.glob("*.part*"))


@CAN_FFMPEG
def test_meme_thuc_su_hien_dung_luc(du_an):
    """Lấy khung hình trước và trong lúc meme hiện, hai khung phải khác nhau ở góc dưới phải."""
    tmp_path, video = du_an
    settings = load_settings(env={"OUTPUT_PRESET": "ultrafast"}, root=tmp_path)
    timeline = Timeline(video=video.name, events=[
        MemeEvent(id="e1", start=2.0, duration=1.0, asset="assets/memes/meme.png")])
    save_timeline(tmp_path / "tl.json", timeline)
    out, _ = render_timeline(video, settings, timeline_path=tmp_path / "tl.json")

    def goc_duoi_phai(t: float) -> bytes:
        anh = tmp_path / f"frame_{t}.png"
        run_cmd(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", str(t),
                 "-i", str(out), "-frames:v", "1", "-vf", "crop=120:80:520:280", str(anh)])
        return anh.read_bytes()

    assert goc_duoi_phai(2.5) != goc_duoi_phai(0.5)   # có meme ≠ chưa có meme
    assert goc_duoi_phai(4.5) != goc_duoi_phai(2.5)   # meme đã tắt


@CAN_FFMPEG
def test_render_meme_video_mp4_that(du_an):
    tmp_path, video = du_an
    meme_video = tmp_path / "assets" / "memes" / "reaction.mp4"
    run_cmd([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=blue:size=120x80:rate=25:duration=0.4",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(meme_video),
    ])
    settings = load_settings(env={"OUTPUT_PRESET": "ultrafast"}, root=tmp_path)
    timeline_path = tmp_path / "video-meme.timeline.json"
    save_timeline(timeline_path, Timeline(video=video.name, events=[
        MemeEvent(
            id="video-meme",
            start=1.0,
            duration=1.5,
            asset="assets/memes/reaction.mp4",
        ),
    ]))
    output = tmp_path / "video-meme-output.mp4"
    out, _ = render_timeline(
        video,
        settings,
        timeline_path=timeline_path,
        output=output,
    )
    assert out.is_file() and probe(out).duration == pytest.approx(5.0, abs=0.2)


@CAN_FFMPEG
def test_render_lai_thi_bo_qua_tru_khi_force(du_an):
    tmp_path, video = du_an
    settings = load_settings(env={"OUTPUT_PRESET": "ultrafast"}, root=tmp_path)
    save_timeline(tmp_path / "tl.json", Timeline(video=video.name, events=[
        MemeEvent(id="e1", start=1.0, duration=1.0, asset="assets/memes/meme.png")]))

    out, _ = render_timeline(video, settings, timeline_path=tmp_path / "tl.json")
    lan_dau = out.stat().st_mtime_ns
    render_timeline(video, settings, timeline_path=tmp_path / "tl.json")
    assert out.stat().st_mtime_ns == lan_dau
    render_timeline(video, settings, timeline_path=tmp_path / "tl.json", force=True)
    assert out.stat().st_mtime_ns != lan_dau


@CAN_FFMPEG
def test_render_tu_lam_lai_khi_timeline_doi(du_an):
    tmp_path, video = du_an
    settings = load_settings(env={"OUTPUT_PRESET": "ultrafast"}, root=tmp_path)
    timeline_path = tmp_path / "tl.json"
    timeline = Timeline(video=video.name, events=[
        MemeEvent(id="e1", start=1.0, duration=1.0, asset="assets/memes/meme.png")])
    save_timeline(timeline_path, timeline)
    out, _ = render_timeline(video, settings, timeline_path=timeline_path)
    before = out.stat().st_mtime_ns

    timeline.events[0].reason = "đã duyệt bằng tay"
    save_timeline(timeline_path, timeline)
    render_timeline(video, settings, timeline_path=timeline_path)
    assert out.stat().st_mtime_ns != before


@CAN_FFMPEG
def test_output_bi_sua_ngoai_automeme_khong_bi_ghi_de(du_an):
    tmp_path, video = du_an
    settings = load_settings(env={"OUTPUT_PRESET": "ultrafast"}, root=tmp_path)
    timeline_path = tmp_path / "tl.json"
    save_timeline(timeline_path, Timeline(video=video.name, events=[
        MemeEvent(id="e1", start=1.0, duration=1.0, asset="assets/memes/meme.png")]))
    out, _ = render_timeline(video, settings, timeline_path=timeline_path)

    out.write_bytes(b"nguoi dung da thay output")
    render_timeline(video, settings, timeline_path=timeline_path)
    assert out.read_bytes() == b"nguoi dung da thay output"


@CAN_FFMPEG
def test_dung_han_khi_timeline_sai(du_an):
    tmp_path, video = du_an
    settings = load_settings(env={}, root=tmp_path)
    save_timeline(tmp_path / "tl.json", Timeline(video=video.name, events=[
        MemeEvent(id="e1", start=1.0, duration=1.0, asset="assets/memes/khong_co.png")]))
    with pytest.raises(ValueError, match="không thấy file meme"):
        render_timeline(video, settings, timeline_path=tmp_path / "tl.json")


def test_bao_loi_khi_chua_co_timeline(tmp_path):
    settings = load_settings(env={}, root=tmp_path)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"gia")
    with pytest.raises(FileNotFoundError, match="Chưa có timeline"):
        render_timeline(video, settings)


def test_render_video_khong_ton_tai(tmp_path):
    settings = load_settings(env={}, root=tmp_path)
    with pytest.raises(FileNotFoundError, match="Không thấy video"):
        render_timeline(tmp_path / "khong_co.mp4", settings)


@CAN_FFMPEG
def test_render_ghi_file_tam_roi_doi_ten(du_an):
    """Nếu FFmpeg lỗi thì không được để lại file output dở dang."""
    tmp_path, video = du_an
    plan = _plan([_event()], [tmp_path / "khong_co.png"])
    out = tmp_path / "out.mp4"
    with pytest.raises(CommandError):
        render(video, out, plan, video_codec="libx264", crf=30, preset="ultrafast",
               audio_codec="aac")
    assert not out.exists()
    assert not list(tmp_path.glob("*.part*"))
