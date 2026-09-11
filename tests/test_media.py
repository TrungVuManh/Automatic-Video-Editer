from pathlib import Path

import pytest

from automeme.media.audio import build_extract_audio_cmd, extract_audio
from automeme.media.ffmpeg import parse_ffmpeg_version, run_cmd, which
from automeme.media.probe import parse_probe, probe


def test_lenh_tach_audio_mono_16k_pcm():
    cmd = build_extract_audio_cmd(Path("video có dấu cách.mp4"), Path("out.wav"))
    assert cmd[0] == "ffmpeg"
    assert cmd[cmd.index("-ac") + 1] == "1"
    assert cmd[cmd.index("-ar") + 1] == "16000"
    assert cmd[cmd.index("-c:a") + 1] == "pcm_s16le"
    assert "-vn" in cmd
    # đường dẫn có dấu cách là MỘT phần tử của list, không bị tách
    assert cmd[cmd.index("-i") + 1] == str(Path("video có dấu cách.mp4"))
    assert cmd[-1] == "out.wav"


def test_parse_probe_video_co_audio():
    info = parse_probe({
        "streams": [
            {"codec_type": "video", "width": 1920, "height": 1080,
             "avg_frame_rate": "30000/1001", "r_frame_rate": "30000/1001"},
            {"codec_type": "audio", "sample_rate": "48000", "channels": 2},
        ],
        "format": {"duration": "47.830000", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
    })
    assert info.duration == pytest.approx(47.83)
    assert (info.width, info.height) == (1920, 1080)
    assert info.fps == pytest.approx(29.97)
    assert info.has_video and info.has_audio
    assert (info.audio_sample_rate, info.audio_channels) == (48000, 2)


def test_parse_probe_bo_qua_anh_bia():
    info = parse_probe({"streams": [
        {"codec_type": "video", "width": 600, "height": 600, "disposition": {"attached_pic": 1}},
        {"codec_type": "video", "width": 1280, "height": 720, "avg_frame_rate": "25/1"},
    ], "format": {"duration": "5"}})
    assert (info.width, info.height) == (1280, 720)


def test_parse_probe_anh_tinh():
    info = parse_probe({
        "streams": [{"codec_type": "video", "width": 500, "height": 400,
                     "avg_frame_rate": "0/0", "r_frame_rate": "25/1"}],
        "format": {"format_name": "png_pipe"},
    })
    assert info.duration is None
    assert info.fps == 25.0
    assert not info.has_audio
    assert info.audio_sample_rate is None
    assert info.format_name == "png_pipe"


def test_parse_probe_lay_thoi_luong_tu_stream_khi_format_thieu():
    info = parse_probe({"streams": [
        {"codec_type": "video", "duration": "4.9"},
        {"codec_type": "audio", "duration": "5.0"},
    ], "format": {"duration": "N/A"}})
    assert info.duration == 5.0


def test_parse_probe_rong():
    info = parse_probe({})
    assert info.duration is None and not info.has_video and not info.has_audio


@pytest.mark.parametrize("text, expected", [
    ("ffmpeg version 9.0.1-full_build-www.gyan.dev Copyright (c) 2000-2026",
     "9.0.1-full_build-www.gyan.dev"),
    ("ffprobe version n7.1 Copyright", "n7.1"),
    ("rác", None),
    ("", None),
])
def test_parse_ffmpeg_version(text, expected):
    assert parse_ffmpeg_version(text) == expected


@pytest.mark.skipif(not (which("ffmpeg") and which("ffprobe")), reason="cần FFmpeg")
def test_tach_audio_that_tren_video_tu_sinh(tmp_path):
    video = tmp_path / "mẫu thử.mp4"  # tên có dấu tiếng Việt và dấu cách
    run_cmd(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=2",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-shortest", str(video)])
    v = probe(video)
    assert v.has_video and v.has_audio
    assert (v.width, v.height) == (320, 240)
    assert v.duration == pytest.approx(2, abs=0.2)

    audio = extract_audio(video, tmp_path / "audio.wav")
    a = probe(audio)
    assert not a.has_video
    assert (a.audio_sample_rate, a.audio_channels) == (16000, 1)
    assert a.duration == pytest.approx(2, abs=0.2)
    assert not list(tmp_path.glob("*.part*"))

    # Chạy lại: đã có output thì bỏ qua, không ghi lại
    mtime = audio.stat().st_mtime_ns
    extract_audio(video, audio)
    assert audio.stat().st_mtime_ns == mtime


def test_tach_audio_video_khong_ton_tai(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_audio(tmp_path / "khong_co.mp4", tmp_path / "a.wav")
