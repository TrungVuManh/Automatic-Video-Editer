import json

import pytest

from automeme.analyzer.schema import Analysis, MemeOpportunity
from automeme.config import load_settings
from automeme.sfx.library import (
    LocalSfxProvider,
    _validate_sfx_url,
    install_popular_sfx,
    load_sfx_catalog,
    parse_sfx_library,
)
from automeme.sfx.schema import SfxCandidate
from automeme.timeline.builder import build_timeline
from automeme.timeline.schema import SfxEvent, parse_timeline


class FakeResponse:
    status_code = 200
    headers = {"content-type": "audio/ogg", "content-length": "12"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def raise_for_status(self):
        return None

    def iter_bytes(self):
        yield b"OggSfake-audio"


class FakeClient:
    def __init__(self):
        self.urls = []
        self.closed = False

    def stream(self, method, url):
        assert method == "GET"
        self.urls.append(url)
        return FakeResponse()

    def close(self):
        self.closed = True


def test_catalog_co_30_sfx_da_dan_nhan_song_ngu():
    items = load_sfx_catalog()
    assert len(items) == 30
    assert len({item.id for item in items}) == 30
    assert all(item.file.endswith(".ogg") for item in items)
    assert any("thất bại" in item.tags for item in items)
    assert any("success" in item.tags for item in items)


def test_cai_sfx_atomic_va_chay_lai_dung_cache(tmp_path):
    settings = load_settings(env={}, root=tmp_path)
    client = FakeClient()
    first = install_popular_sfx(
        settings, client_factory=lambda **_kwargs: client,
    )
    second = install_popular_sfx(
        settings, client_factory=lambda **_kwargs: FakeClient(),
    )

    assert (first.installed, first.failed, second.reused) == (30, 0, 30)
    assert client.closed and len(client.urls) == 30
    items, warnings = parse_sfx_library(settings.sfx.library_file.read_text(encoding="utf-8"))
    assert not warnings and len(items) == 30
    assert all(item.source_url and "CC0" in (item.license_note or "") for item in items)
    assert all(path.read_bytes().startswith(b"OggS") for path in (
        settings.paths.assets_dir / "sfx" / "popular"
    ).iterdir())


def test_provider_tim_duoc_sfx_bang_tu_khoa_viet(tmp_path):
    settings = load_settings(env={}, root=tmp_path)
    install_popular_sfx(settings, client_factory=lambda **_kwargs: FakeClient())
    provider = LocalSfxProvider(
        library_file=settings.sfx.library_file,
        project_root=tmp_path,
    )
    assert provider.search("thất bại")[0].id in {"kenney-fail-error", "kenney-fail-low"}
    assert provider.search("chuyển cảnh")[0].type == "audio"
    assert provider.materialize(provider.search("vỡ kính")[0]).is_file()


@pytest.mark.parametrize("url", [
    "http://raw.githubusercontent.com/chenisan/AudioSFX/bad/a.ogg",
    "https://evil.example/a.ogg",
    "https://raw.githubusercontent.com/chenisan/AudioSFX/main/assets/sfx-library/files/a.ogg",
    "https://raw.githubusercontent.com/chenisan/AudioSFX/fa851a79288bf0ee81cdf6faa9430bbbed48b292/README.md",
])
def test_chi_tai_tu_revision_github_da_ghim(url):
    with pytest.raises(ValueError):
        _validate_sfx_url(url)


def test_timeline_doc_cu_va_sfx_cung_doc_duoc():
    timeline = parse_timeline({
        "video": "clip.mp4",
        "events": [
            {"id": "old", "start": 0, "duration": 1, "asset": "meme.png"},
            {
                "id": "sound", "type": "sfx", "start": 1, "duration": 0.5,
                "asset": "hit.ogg", "volume": 0.3,
            },
        ],
    })
    assert timeline.events[0].type == "meme"
    assert isinstance(timeline.events[1], SfxEvent)


def test_builder_tao_sfx_tu_goi_y_ai(tmp_path):
    settings = load_settings(env={}, root=tmp_path)
    asset = tmp_path / "hit.ogg"
    asset.write_bytes(b"OggS")
    sound = SfxCandidate(
        id="hit", filename=str(asset), tags=["impact", "nhấn mạnh"],
        duration=0.6, quality=0.9, recommended_volume=0.8,
    )

    class MemeProvider:
        def search(self, _query, _limit=10):
            return []

    class SoundProvider:
        def search(self, _query, _limit=10):
            return [sound.model_copy(update={"semantic_score": 1.0})]

        def materialize(self, _item):
            return asset

    opportunity = MemeOpportunity.model_validate({
        "segment_id": 0, "insert_meme": False, "insert_sfx": True,
        "sfx_query": "impact", "confidence": 0.9, "trigger": "punchline",
        "reason": "nhấn mạnh", "emotion": "", "reaction_type": "",
        "search_query": "", "preferred_style": "",
        "timing": {"anchor": 1, "delay": 0.15, "duration": 1},
    })
    timeline = build_timeline(
        Analysis(video="clip.mp4", backend="test", model="test", opportunities=[opportunity]),
        MemeProvider(), settings.ranking, top_k=10, project_root=tmp_path,
        video_duration=5, sfx_provider=SoundProvider(), sfx_settings=settings.sfx,
    )
    assert len(timeline.events) == 1
    event = timeline.events[0]
    assert isinstance(event, SfxEvent)
    assert event.asset == "hit.ogg" and event.volume == pytest.approx(0.28)


def test_sfx_schema_tu_choi_metadata_la(tmp_path):
    candidate = SfxCandidate(
        id="x", filename="x.ogg", duration=0.2, tags=["click"],
    )
    raw = json.dumps({**candidate.model_dump(), "unknown": True})
    items, warnings = parse_sfx_library(raw)
    assert not items and warnings
