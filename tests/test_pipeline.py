import pytest

from automeme.config import load_settings
from automeme.media.ffmpeg import run_cmd, which
from automeme.media.probe import MediaInfo
from automeme.pipeline import transcribe_video
from automeme.transcription.base import Transcriber
from automeme.utils.files import read_json
from automeme.workspace import paths_for

RAW = {
    "language": "vi",
    "duration": 2.0,
    "segments": [{"start": 0.1, "end": 1.9, "text": "Vợ tôi giữ hộ.",
                  "words": [{"w": "Vợ", "start": 0.1, "end": 0.4},
                            {"w": "tôi", "start": 0.4, "end": 0.7}]}],
}


class TranscriberGia(Transcriber):
    """Đếm số lần được gọi — để kiểm tra việc bỏ qua khi đã có kết quả."""

    def __init__(self, raw=None):
        self.raw = raw or RAW
        self.so_lan = 0
        self.da_unload = False

    def transcribe(self, audio):
        self.so_lan += 1
        assert audio.exists(), "phải tách audio trước khi nhận dạng"
        return self.raw

    def unload(self):
        self.da_unload = True


@pytest.fixture
def settings(tmp_path):
    return load_settings(env={}, root=tmp_path)


@pytest.fixture
def video_gia(tmp_path, monkeypatch):
    """Video giả + FFmpeg giả: kiểm tra được luồng mà không cần FFmpeg thật."""
    video = tmp_path / "Vợ tôi.mp4"
    video.write_bytes(b"khong phai video that")

    def tach_audio_gia(video, audio, *, force=False):
        audio.parent.mkdir(parents=True, exist_ok=True)
        if not audio.exists() or force:
            audio.write_bytes(b"RIFF....WAVE")
        return audio

    monkeypatch.setattr("automeme.pipeline.extract_audio", tach_audio_gia)
    monkeypatch.setattr("automeme.pipeline.probe", lambda p: MediaInfo(
        duration=2.0, width=1920, height=1080, fps=30.0, has_video=True, has_audio=True,
        audio_sample_rate=48000, audio_channels=2, format_name="mp4"))
    return video


def test_ghi_ca_cache_lan_ban_chinh_thuc(video_gia, settings):
    path, data = transcribe_video(video_gia, settings, transcriber=TranscriberGia())
    paths = paths_for(video_gia, settings)

    assert path == paths.transcript
    assert paths.transcript.exists() and paths.transcript_cache.exists()
    assert read_json(paths.transcript) == data
    assert data["video"] == "Vợ tôi.mp4"       # tên gốc giữ nguyên dấu trong nội dung
    assert paths.transcript.name == "vo-toi.json"  # tên file thì bỏ dấu
    assert data["duration"] == 2.0 and data["model"] == settings.whisper.model
    assert len(data["segments"]) == 1 and len(data["words"]) == 2


def test_chay_lai_thi_bo_qua_nhan_dang(video_gia, settings):
    t = TranscriberGia()
    transcribe_video(video_gia, settings, transcriber=t)
    transcribe_video(video_gia, settings, transcriber=t)
    assert t.so_lan == 1


def test_force_thi_nhan_dang_lai(video_gia, settings):
    t = TranscriberGia()
    transcribe_video(video_gia, settings, transcriber=t)
    transcribe_video(video_gia, settings, transcriber=t, force=True)
    assert t.so_lan == 2


def test_doi_model_thi_nhan_dang_lai(video_gia, tmp_path):
    t = TranscriberGia()
    transcribe_video(video_gia, load_settings(env={}, root=tmp_path), transcriber=t)
    transcribe_video(video_gia, load_settings(env={"WHISPER_MODEL": "medium"}, root=tmp_path),
                     transcriber=t)
    assert t.so_lan == 2


def test_video_khong_ton_tai(tmp_path, settings):
    with pytest.raises(FileNotFoundError, match="Không thấy video"):
        transcribe_video(tmp_path / "khong_co.mp4", settings, transcriber=TranscriberGia())


def test_canh_bao_duoc_ghi_log(video_gia, settings, caplog):
    t = TranscriberGia({"language": "vi", "duration": 2.0,
                        "segments": [{"start": 0, "end": 1, "text": "a", "words": []}]})
    with caplog.at_level("WARNING", logger="automeme"):
        transcribe_video(video_gia, settings, transcriber=t)
    assert any("timestamp theo từ" in r.getMessage() for r in caplog.records)


@pytest.mark.skipif(not (which("ffmpeg") and which("ffprobe")), reason="cần FFmpeg")
def test_tach_audio_that_roi_nhan_dang(tmp_path, settings):
    """Nối thật với FFmpeg: video → audio 16 kHz mono → transcript (nhận dạng vẫn giả lập)."""
    video = tmp_path / "clip thử.mp4"
    run_cmd(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=2",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-shortest", str(video)])

    t = TranscriberGia()
    path, data = transcribe_video(video, settings, transcriber=t)
    paths = paths_for(video, settings)
    assert paths.audio.exists() and path.exists()
    assert t.da_unload is False  # transcriber do test truyền vào thì pipeline không tự unload
    assert data["duration"] == pytest.approx(2.0, abs=0.2)  # lấy từ ffprobe, không phải backend
