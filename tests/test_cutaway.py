"""Meme tràn màn hình (cutaway), zoom, hạ tiếng gốc và chặn đỉnh âm."""
import re
from pathlib import Path

import pytest

from automeme.config import load_settings
from automeme.media.ffmpeg import run_cmd, which
from automeme.media.probe import probe
from automeme.pipeline import render_timeline
from automeme.rendering.filters import (
    CutawayStyle,
    build_render_plan,
    duck_expr,
    zoom_expr,
)
from automeme.timeline.schema import (
    MemeEvent,
    SfxEvent,
    Timeline,
    TimelineError,
    ZoomEvent,
    parse_timeline,
    save_timeline,
)
from automeme.timeline.validator import validate_timeline

CAN_FFMPEG = pytest.mark.skipif(not (which("ffmpeg") and which("ffprobe")), reason="cần FFmpeg")


def _plan(events, assets, **kw):
    cfg = {"video_w": 1920, "video_h": 1080, "scale_default": 0.3,
           "position_default": "bottom-right", "margin_ratio": 0.03, "max_height_ratio": 0.45,
           "fps": 60}
    return build_render_plan(events, assets, **{**cfg, **kw})


def _cut(**kw):
    return MemeEvent(**{"id": "c1", "start": 10.0, "duration": 1.2, "asset": "a.gif",
                        "mode": "cutaway", **kw})


# ------------------------------------------------------------------ filtergraph (hàm thuần)
def test_cutaway_nen_mo_meme_vua_khung_vao_khung_mem():
    fc = _plan([_cut()], [Path("a.gif")]).filter_complex
    assert "[1:v]fps=60,split=2[cb0][cf0]" in fc
    # nền = chính meme phóng lấp khung rồi làm mờ + tối
    assert "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,boxblur=24:2" in fc
    assert "eq=brightness=-0.18" in fc
    # meme vừa 92% khung, giữ tỉ lệ
    assert "scale=w=1766:h=992:force_original_aspect_ratio=decrease" in fc
    # vào khung ở 106% rồi thu về 100% trong 0,15 s (9 khung ở 60 fps), mờ vào/ra
    assert "zoompan=z='max(1,1.060-0.060*on/9)'" in fc
    assert "fade=t=in:st=0:d=0.060:alpha=1" in fc and "fade=t=out:st=1.120:d=0.080:alpha=1" in fc
    assert "setpts=PTS-STARTPTS+10.000/TB[m0]" in fc
    # phủ toàn khung từ góc trên trái, đúng khoảng thời gian
    assert "[0:v][m0]overlay=0:0:enable='between(t,10.000,11.200)'" in fc


def test_cutaway_ha_tieng_goc_va_chan_dinh():
    plan = _plan([_cut()], [Path("a.gif")])
    assert "[0:a]volume=volume='1-0.650*clip((t-9.920)/0.080,0,1)*clip((11.280-t)/0.080,0,1)'" \
           ":eval=frame[ad]" in plan.filter_complex
    assert "[ad]alimiter=limit=0.891:level=0[a]" in plan.filter_complex
    assert plan.out_audio_label == "[a]"


def test_meme_goc_khong_sfx_thi_giu_nguyen_audio_goc():
    plan = _plan([MemeEvent(id="m", start=1, duration=1, asset="a.png")], [Path("a.png")])
    assert plan.out_audio_label == ""  # copy audio, không encode lại vô ích


def test_video_khong_tieng_thi_khong_ha_tieng():
    plan = _plan([_cut()], [Path("a.gif")], has_audio=False)
    assert "volume=" not in plan.filter_complex and plan.out_audio_label == ""


def test_cutaway_cung_sfx_tron_sau_khi_ha_tieng():
    events = [_cut(), SfxEvent(id="s1", start=10.0, duration=0.5, asset="boom.ogg", volume=0.3)]
    fc = _plan(events, [Path("a.gif"), Path("boom.ogg")]).filter_complex
    assert "[2:a]atrim=0:0.500" in fc  # SFX là input thứ 2
    assert "[ad][s0]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[am]" in fc
    assert "[am]alimiter=limit=0.891:level=0[a]" in fc


def test_zoom_khong_chiem_input_va_di_truoc_meme():
    events = [ZoomEvent(id="z1", start=9.7, duration=0.4, factor=1.1), _cut()]
    plan = _plan(events, [None, Path("a.gif")])
    fc = plan.filter_complex
    assert plan.input_args.count("-i") == 1  # zoom không có file
    assert fc.startswith("[0:v]zoompan=z='1+0.100*clip((on/60-9.700)/0.120,0,1)")
    assert ":d=1:s=1920x1080:fps=60,setsar=1[vz]" in fc
    assert "[vz][m0]overlay=0:0" in fc


def test_chi_co_zoom_thi_video_ra_la_ket_qua_zoom():
    plan = _plan([ZoomEvent(id="z1", start=2, duration=0.5)], [None])
    assert plan.filter_complex.endswith("setsar=1[v]") and plan.out_label == "[v]"
    assert plan.out_audio_label == ""


def test_bieu_thuc_zoom_va_ha_tieng_nhieu_su_kien():
    z = [ZoomEvent(id="a", start=1, duration=0.3, factor=1.1),
         ZoomEvent(id="b", start=5, duration=0.3, factor=1.2)]
    assert zoom_expr(z, 30, 0.12).startswith("max(1+0.100*clip((on/30-1.000)")
    cuts = [_cut(id="c1", start=1), _cut(id="c2", start=20)]
    assert duck_expr(cuts, 0.35, 0.08).startswith("min(1-0.650*clip((t-0.920)")


def test_style_lay_tu_cau_hinh():
    from automeme.rendering.filters import cutaway_style

    style = cutaway_style(load_settings(env={}).cutaway)
    assert style == CutawayStyle()  # mặc định trong configs/ khớp mặc định trong code


# ------------------------------------------------------------------ schema + validator
def test_su_kien_phan_loai_theo_type_va_timeline_cu_van_doc_duoc():
    tl = parse_timeline({"video": "a.mp4", "events": [
        {"id": "m", "start": 1, "duration": 1, "asset": "a.png"},          # timeline cũ, không type
        {"id": "z", "type": "zoom", "start": 2, "duration": 0.3, "factor": 1.15},
        {"id": "c", "type": "meme", "mode": "cutaway", "start": 5, "duration": 1,
         "asset": "b.gif"},
    ]})
    assert [type(e).__name__ for e in tl.events] == ["MemeEvent", "ZoomEvent", "MemeEvent"]
    assert tl.events[2].mode == "cutaway"


def test_meme_thieu_asset_khong_bi_hieu_nham_thanh_zoom():
    with pytest.raises(TimelineError, match="asset"):
        parse_timeline({"video": "a.mp4", "events": [{"id": "e", "start": 1, "duration": 1}]})


@pytest.mark.parametrize("sua", [{"factor": 2.0}, {"duration": 5}, {"asset": "x.png"}])
def test_zoom_sai_bi_bat(sua):
    with pytest.raises(TimelineError, match="type=zoom"):
        parse_timeline({"video": "a.mp4", "events": [
            {"id": "z", "type": "zoom", "start": 1, "duration": 0.3, **sua}]})


def _loi(*events, duration=60):
    tl = Timeline(video="a.mp4", events=list(events))
    paths = {e.asset: Path(e.asset) for e in events if hasattr(e, "asset")}
    return validate_timeline(tl, video_duration=duration, asset_paths=paths,
                             ton_tai=lambda p: True)[0]


def test_hai_cu_cat_tran_man_hinh_trung_gio_la_loi():
    loi = _loi(_cut(id="c1", start=10), _cut(id="c2", start=10.5))
    assert any("cùng tràn màn hình" in e for e in loi)


def test_meme_goc_trong_luc_cat_tran_man_hinh_la_loi():
    """Renderer vẽ meme theo thứ tự sự kiện: meme góc bắt đầu sau sẽ đè lên cú cắt tràn màn hình."""
    goc = MemeEvent(id="m", start=10.2, duration=1, asset="b.png", position="bottom-right")
    assert any("chồng lên meme tràn màn hình" in e for e in _loi(_cut(), goc))
    sau = MemeEvent(id="m", start=12, duration=1, asset="b.png", position="bottom-right")
    assert _loi(_cut(), sau) == []


def test_zoom_trung_nhau_la_loi_nhung_khong_can_file():
    loi = _loi(ZoomEvent(id="z1", start=1, duration=0.5), ZoomEvent(id="z2", start=1.2,
                                                                     duration=0.5))
    assert any("hai zoom trùng thời gian" in e for e in loi)
    assert not any("không thấy file" in e for e in loi)


# ------------------------------------------------------------------ render thật
@pytest.fixture
def du_an(tmp_path):
    (tmp_path / "assets" / "memes").mkdir(parents=True)
    (tmp_path / "assets" / "sfx").mkdir(parents=True)
    video = tmp_path / "clip.mp4"
    run_cmd(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=5",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-shortest", str(video)])
    run_cmd(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
             "-i", "color=c=0x22cc88:size=120x200:rate=10:duration=1",  # GIF khổ dọc
             str(tmp_path / "assets" / "memes" / "doc.gif")])
    run_cmd(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
             "-i", "color=c=red:size=100x80", "-frames:v", "1",
             str(tmp_path / "assets" / "memes" / "goc.png")])
    run_cmd(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
             "-i", "sine=frequency=880:duration=0.4",
             str(tmp_path / "assets" / "sfx" / "boom.wav")])
    return tmp_path, video


def _khung(video: Path, t: float, out: Path) -> Path:
    run_cmd(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", str(t), "-i",
             str(video), "-frames:v", "1", "-vf", "crop=80:80:0:0", str(out)])  # góc trên trái
    return out


def _psnr(a: Path, b: Path) -> float:
    """Độ giống nhau của hai ảnh (dB): cao = gần như y hệt, thấp = khác hẳn."""
    import subprocess

    # FFmpeg in kết quả psnr ra stderr, nên gọi subprocess trực tiếp thay vì run_cmd
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(a), "-i", str(b), "-lavfi", "psnr",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    match = re.search(r"average:(inf|[\d.]+)", out)
    return float("inf") if match.group(1) == "inf" else float(match.group(1))


@CAN_FFMPEG
def test_render_that_cutaway_zoom_meme_goc_va_sfx(du_an):
    tmp_path, video = du_an
    settings = load_settings(env={"OUTPUT_PRESET": "ultrafast"}, root=tmp_path)
    save_timeline(tmp_path / "tl.json", Timeline(video=video.name, events=[
        ZoomEvent(id="z1", start=0.7, duration=0.4, factor=1.12),
        MemeEvent(id="c1", start=1.0, duration=1.2, asset="assets/memes/doc.gif", mode="cutaway"),
        SfxEvent(id="s1", start=1.0, duration=0.4, asset="assets/sfx/boom.wav", volume=0.4),
        MemeEvent(id="m1", start=3.0, duration=1.0, asset="assets/memes/goc.png"),
    ]))
    out, _ = render_timeline(video, settings, timeline_path=tmp_path / "tl.json")

    goc, moi = probe(video), probe(out)
    assert moi.duration == pytest.approx(goc.duration, abs=0.15)  # không kéo dài video
    assert (moi.width, moi.height) == (640, 360) and moi.has_audio

    # Tràn màn hình: cả góc trên trái cũng đổi hẳn so với nguồn (PSNR thấp)
    goc_1 = _khung(video, 1.6, tmp_path / "g1.png")
    assert _psnr(goc_1, _khung(out, 1.6, tmp_path / "o1.png")) < 20
    # Meme ở góc dưới phải: góc trên trái gần như giữ nguyên (PSNR cao)
    goc_2 = _khung(video, 3.5, tmp_path / "g2.png")
    assert _psnr(goc_2, _khung(out, 3.5, tmp_path / "o2.png")) > 25
