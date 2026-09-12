import pytest

from automeme.analyzer.base import StructuredLLM
from automeme.analyzer.schema import Analysis, MemeOpportunity, save_analysis
from automeme.config import load_settings
from automeme.media.ffmpeg import run_cmd, which
from automeme.media.probe import MediaInfo, probe
from automeme.memes.base import MemeProvider
from automeme.memes.schema import MemeCandidate
from automeme.pipeline import analyze_video, build_video_timeline, run_video, transcribe_video
from automeme.timeline.schema import Timeline, save_timeline
from automeme.transcription.base import Transcriber
from automeme.utils.files import read_json, write_json
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


class AnalysisLLMGia(StructuredLLM):
    model = "llm-gia"

    def __init__(self):
        self.so_lan = 0

    def complete(self, prompt, schema):
        self.so_lan += 1
        return """{
          "segment_id": 0,
          "insert_meme": true,
          "confidence": 0.9,
          "trigger": "punchline",
          "reason": "câu trả lời bất ngờ",
          "emotion": "bối rối",
          "reaction_type": "confused reaction",
          "search_query": "confused man reaction",
          "preferred_style": "reaction",
          "timing": {"anchor": 0.5, "delay": 0.1, "duration": 4.0}
        }"""


class MemeProviderGia(MemeProvider):
    def __init__(self, asset):
        self.asset = asset
        self.so_lan = 0

    def search(self, query, limit=10):
        self.so_lan += 1
        return [MemeCandidate(
            id="confused",
            filename=str(self.asset),
            type="image",
            tags=["confused", "reaction"],
            emotion=["bối rối"],
            style=["reaction"],
            semantic_score=0.9,
        )]

    def materialize(self, candidate):
        return self.asset


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


def _ghi_transcript_cho_analyze(video, settings):
    paths = paths_for(video, settings)
    write_json(paths.transcript, {
        "video": video.name,
        "language": "vi",
        "duration": 20.0,
        "model": "large-v3",
        "segments": [{"id": 0, "start": 1.0, "end": 2.0, "text": "Vợ tôi giữ hộ."}],
        "words": [],
    })
    return paths


def test_analyze_ghi_schema_va_ap_rang_buoc_cung(video_gia, settings):
    paths = _ghi_transcript_cho_analyze(video_gia, settings)
    llm = AnalysisLLMGia()
    path, analysis = analyze_video(video_gia, settings, llm=llm)

    assert path == paths.analysis and path.exists()
    assert read_json(path)["model"] == "llm-gia"
    assert len(analysis.opportunities) == 1
    timing = analysis.opportunities[0].timing
    assert timing.anchor == 2.0                  # code lấy cuối câu, không tin anchor 0.5
    assert timing.delay == settings.analyzer.timing_delay
    assert timing.duration == settings.meme.duration_max  # kẹp 4.0 xuống 2.5


def test_analyze_chay_lai_bo_qua_llm_va_force_chay_lai(video_gia, settings):
    _ghi_transcript_cho_analyze(video_gia, settings)
    llm = AnalysisLLMGia()
    analyze_video(video_gia, settings, llm=llm)
    analyze_video(video_gia, settings, llm=llm)
    assert llm.so_lan == 1
    analyze_video(video_gia, settings, llm=llm, force=True)
    assert llm.so_lan == 2


def test_analyze_tu_vo_hieu_cache_khi_cau_hinh_hoac_video_doi(
        video_gia, settings, tmp_path):
    _ghi_transcript_cho_analyze(video_gia, settings)
    llm = AnalysisLLMGia()
    analyze_video(video_gia, settings, llm=llm)

    changed = load_settings(
        env={"MEME_SCORE_THRESHOLD": "0.7"}, root=tmp_path,
    )
    analyze_video(video_gia, changed, llm=llm)
    assert llm.so_lan == 2

    video_gia.write_bytes(b"noi dung video da doi")
    analyze_video(video_gia, changed, llm=llm)
    assert llm.so_lan == 3


def test_analyze_thieu_transcript_bao_lenh_can_chay(video_gia, settings):
    with pytest.raises(FileNotFoundError, match="automeme transcribe"):
        analyze_video(video_gia, settings, llm=AnalysisLLMGia())


def _ghi_analysis_cho_timeline(video, settings):
    paths = paths_for(video, settings)
    opportunity = MemeOpportunity.model_validate({
        "segment_id": 0,
        "insert_meme": True,
        "confidence": 0.9,
        "trigger": "punchline",
        "reason": "bất ngờ",
        "emotion": "bối rối",
        "reaction_type": "confused reaction",
        "search_query": "confused reaction",
        "preferred_style": "reaction",
        "timing": {"anchor": 0.5, "delay": 0.15, "duration": 0.8},
    })
    save_analysis(paths.analysis, Analysis(
        video=video.name,
        backend="ollama",
        model="fake",
        opportunities=[opportunity],
    ))
    return paths


def test_build_video_timeline_ghi_file_va_resume(video_gia, settings, tmp_path):
    paths = _ghi_analysis_cho_timeline(video_gia, settings)
    asset = tmp_path / "assets" / "memes" / "confused.png"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"PNG")
    provider = MemeProviderGia(asset)

    path, timeline = build_video_timeline(video_gia, settings, provider=provider)
    assert path == paths.timeline and path.exists() and len(timeline.events) == 1
    assert timeline.events[0].asset == "assets/memes/confused.png"
    build_video_timeline(video_gia, settings, provider=provider)
    assert provider.so_lan == 1
    build_video_timeline(video_gia, settings, provider=provider, force=True)
    assert provider.so_lan == 2


def test_timeline_tu_lam_moi_khi_ranking_doi(video_gia, settings, tmp_path):
    _ghi_analysis_cho_timeline(video_gia, settings)
    asset = tmp_path / "assets" / "memes" / "confused.png"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"PNG")
    provider = MemeProviderGia(asset)
    build_video_timeline(video_gia, settings, provider=provider)

    changed = load_settings(
        env={}, root=tmp_path, overrides={"ranking": {"duplicate_penalty": 0.4}},
    )
    build_video_timeline(video_gia, changed, provider=provider)
    assert provider.so_lan == 2


def test_timeline_chinh_tay_khong_bi_ghi_de(video_gia, settings, tmp_path):
    paths = _ghi_analysis_cho_timeline(video_gia, settings)
    asset = tmp_path / "assets" / "memes" / "confused.png"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"PNG")
    provider = MemeProviderGia(asset)
    _, timeline = build_video_timeline(video_gia, settings, provider=provider)

    timeline.events[0].reason = "người dùng đã sửa"
    save_timeline(paths.timeline, timeline)
    _, reused = build_video_timeline(video_gia, settings, provider=provider)

    assert reused.events[0].reason == "người dùng đã sửa"
    assert provider.so_lan == 1


def test_build_video_timeline_thieu_analysis_bao_ro(video_gia, settings):
    with pytest.raises(FileNotFoundError, match="automeme analyze"):
        build_video_timeline(video_gia, settings, provider=MemeProviderGia(video_gia))


def test_run_video_noi_dung_thu_tu_cac_buoc(monkeypatch, video_gia, settings, tmp_path):
    calls = []
    timeline = Timeline(video=video_gia.name)

    monkeypatch.setattr("automeme.pipeline.transcribe_video",
                        lambda *a, **kw: calls.append("transcribe"))
    monkeypatch.setattr("automeme.pipeline.analyze_video",
                        lambda *a, **kw: calls.append("analyze"))

    def build(*args, **kwargs):
        calls.append("timeline")
        return tmp_path / "tl.json", timeline

    def render(*args, **kwargs):
        calls.append("render")
        return tmp_path / "out.mp4", timeline

    monkeypatch.setattr("automeme.pipeline.build_video_timeline", build)
    monkeypatch.setattr("automeme.pipeline.render_timeline", render)
    output, result = run_video(video_gia, settings, force=True)
    assert calls == ["transcribe", "analyze", "timeline", "render"]
    assert output == tmp_path / "out.mp4" and result is timeline


def test_run_video_bao_tien_do_tung_buoc(monkeypatch, video_gia, settings, tmp_path):
    timeline = Timeline(video=video_gia.name)
    monkeypatch.setattr("automeme.pipeline.transcribe_video", lambda *a, **kw: None)
    monkeypatch.setattr("automeme.pipeline.analyze_video", lambda *a, **kw: None)
    monkeypatch.setattr(
        "automeme.pipeline.build_video_timeline",
        lambda *a, **kw: (tmp_path / "tl.json", timeline),
    )
    monkeypatch.setattr(
        "automeme.pipeline.render_timeline",
        lambda *a, **kw: (tmp_path / "out.mp4", timeline),
    )
    progress = []
    run_video(video_gia, settings, progress_callback=lambda stage, status: progress.append(
        (stage, status)
    ))
    assert progress == [
        ("transcribe", "running"), ("transcribe", "completed"),
        ("analyze", "running"), ("analyze", "completed"),
        ("timeline", "running"), ("timeline", "completed"),
        ("render", "running"), ("render", "completed"),
    ]


@pytest.mark.skipif(not (which("ffmpeg") and which("ffprobe")), reason="cần FFmpeg")
def test_run_video_tich_hop_that_voi_backend_gia(tmp_path):
    """Video thật qua đủ pipeline; chỉ Whisper, LLM và tìm kiếm được giả lập."""
    video = tmp_path / "clip.mp4"
    run_cmd(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=5",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-shortest", str(video)])
    asset = tmp_path / "assets" / "memes" / "confused.png"
    asset.parent.mkdir(parents=True)
    run_cmd(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "color=c=red@0.8:size=100x80,format=rgba",
             "-frames:v", "1", str(asset)])
    settings = load_settings(env={"OUTPUT_PRESET": "ultrafast"}, root=tmp_path)

    output, timeline = run_video(
        video,
        settings,
        force=True,
        transcriber=TranscriberGia(),
        llm=AnalysisLLMGia(),
        provider=MemeProviderGia(asset),
    )

    assert output.exists() and len(timeline.events) == 1
    assert probe(output).has_audio
    paths = paths_for(video, settings)
    assert paths.transcript.exists() and paths.analysis.exists() and paths.timeline.exists()
