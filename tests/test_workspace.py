import pytest

from automeme.config import load_settings
from automeme.workspace import KHOI, asr_key, paths_for, slug, video_fingerprint


@pytest.fixture
def settings(tmp_path):
    return load_settings(env={}, root=tmp_path)


def _video(tmp_path, name="phim.mp4", data=b"0123456789"):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_van_tay_on_dinh_va_doi_khi_noi_dung_doi(tmp_path):
    a = _video(tmp_path, "a.mp4", b"noi dung video")
    b = _video(tmp_path, "b.mp4", b"noi dung video")
    c = _video(tmp_path, "c.mp4", b"noi dung video khac")
    assert video_fingerprint(a) == video_fingerprint(a) == video_fingerprint(b)
    assert video_fingerprint(a) != video_fingerprint(c)
    assert len(video_fingerprint(a)) == 8


def test_van_tay_doc_dau_va_cuoi_file_lon(tmp_path):
    goc = b"A" * (KHOI + 100)
    a = _video(tmp_path, "a.mp4", goc)
    doi_cuoi = _video(tmp_path, "b.mp4", goc[:-1] + b"B")
    assert video_fingerprint(a) != video_fingerprint(doi_cuoi)


def test_asr_key_doi_theo_tham_so_anh_huong_ket_qua(tmp_path):
    goc = load_settings(env={}, root=tmp_path)
    assert asr_key(goc.whisper) == asr_key(load_settings(env={}, root=tmp_path).whisper)
    for env in ({"WHISPER_MODEL": "medium"}, {"WHISPER_LANGUAGE": "en"},
                {"WHISPER_BEAM_SIZE": "1"}, {"WHISPER_COMPUTE_TYPE": "int8"},
                {"WHISPER_VAD_FILTER": "false"},
                {"WHISPER_CONDITION_ON_PREVIOUS_TEXT": "true"}):
        assert asr_key(load_settings(env=env, root=tmp_path).whisper) != asr_key(goc.whisper), env


@pytest.mark.parametrize("goc, mong_doi", [
    ("Mẫu Thử 01", "mau-thu-01"),
    ("đá bóng", "da-bong"),
    ("video_2026-09-12", "video_2026-09-12"),
    ("   ", "video"),
    ("!!!", "video"),
])
def test_slug(goc, mong_doi):
    assert slug(goc) == mong_doi


def test_slug_cat_ngan():
    assert len(slug("a" * 100)) == 60


def test_paths_for(tmp_path, settings):
    video = _video(tmp_path, "Bữa Tiệc.mp4")
    paths = paths_for(video, settings)
    van_tay = video_fingerprint(video)

    assert paths.cache_dir.name == f"bua-tiec-{van_tay}"
    assert paths.cache_dir.parent == settings.paths.data_dir / "cache"
    assert paths.audio == paths.cache_dir / "audio.wav"
    assert paths.transcript_cache.name == f"transcript-{asr_key(settings.whisper)}.json"
    assert paths.transcript == settings.paths.data_dir / "transcripts" / "bua-tiec.json"


def test_doi_model_thi_doi_file_cache_nhung_giu_thu_muc(tmp_path):
    video = _video(tmp_path)
    a = paths_for(video, load_settings(env={}, root=tmp_path))
    b = paths_for(video, load_settings(env={"WHISPER_MODEL": "medium"}, root=tmp_path))
    assert a.cache_dir == b.cache_dir
    assert a.audio == b.audio                      # audio không phụ thuộc model
    assert a.transcript_cache != b.transcript_cache
