import json

import pytest

from automeme.analyzer.schema import MemeOpportunity
from automeme.config import load_settings
from automeme.memes.animated import (
    gif_frame_count,
    install_animated_gifs,
    load_animated_catalog,
)
from automeme.memes.local import LocalMemeProvider, parse_library
from automeme.memes.popular import InstallResult
from automeme.memes.ranker import rank_memes
from automeme.memes.schema import MemeCandidate


def animated_gif(frames=2):
    header = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
    frame = b"\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00"
    return header + frame * frames + b"\x3b"


class FakeResponse:
    status_code = 200
    headers = {"content-type": "image/gif"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def raise_for_status(self):
        return None

    def iter_bytes(self):
        yield animated_gif()


class FakeClient:
    def __init__(self, **_kwargs):
        self.urls = []
        self.closed = False

    def stream(self, method, url):
        assert method == "GET"
        self.urls.append(url)
        return FakeResponse()

    def close(self):
        self.closed = True


def test_catalog_co_30_gif_github_da_ghim_commit():
    catalog = load_animated_catalog()
    assert len(catalog) == 30
    assert len({item.gif_id for item in catalog}) == 30
    assert sum(not item.safe for item in catalog) == 2
    assert all("raw.githubusercontent.com" in str(item.url) for item in catalog)
    assert all(item.labels and item.aliases and item.description for item in catalog)


def test_cai_gif_ghi_metadata_va_tai_su_dung(tmp_path):
    settings = load_settings(env={}, root=tmp_path)
    client = FakeClient()

    first = install_animated_gifs(settings, client_factory=lambda **_kwargs: client)
    second = install_animated_gifs(
        settings,
        client_factory=lambda **_kwargs: FakeClient(),
    )

    assert first == InstallResult(total=30, installed=30, reused=0, failed=0, errors=[])
    assert second.installed == 0 and second.reused == 30 and second.failed == 0
    assert client.closed and len(client.urls) == 30
    items, warnings = parse_library(settings.meme.library_file.read_text(encoding="utf-8"))
    assert not warnings and len(items) == 30
    assert all(item.type == "gif" and item.source_url and item.license_note for item in items)
    assert len(list((settings.paths.assets_dir / "gifs" / "popular").iterdir())) == 30


def test_gif_nhan_song_ngu_tim_dung_phan_ung(tmp_path):
    settings = load_settings(env={}, root=tmp_path)
    install_animated_gifs(settings, client_factory=lambda **_kwargs: FakeClient())
    provider = LocalMemeProvider(
        library_file=settings.meme.library_file,
        asset_dirs=[settings.paths.assets_dir / "gifs"],
        project_root=tmp_path,
    )

    scenarios = {
        "cười lăn laughing hard": "popular-gif-reactionpics-wheeze",
        "nhún vai không chắc": "popular-gif-reactionpics-shrug",
        "gõ phím làm việc gấp": "popular-gif-reactionpics-typing",
        "bối rối nhìn quanh": "popular-gif-snipe-confused-travolta",
        "vỗ tay chậm mỉa mai": "popular-gif-reactionpics-slowclap",
        "nhảy ăn mừng chiến thắng": "popular-gif-snipe-carlton-dance",
    }
    for query, expected in scenarios.items():
        ids = {item.id for item in provider.search(query, limit=10)}
        assert expected in ids, (query, ids)


def test_dem_frame_va_tu_choi_file_tinh():
    assert gif_frame_count(animated_gif(3)) == 3
    assert gif_frame_count(animated_gif(1)) == 1
    with pytest.raises(ValueError, match="header GIF"):
        gif_frame_count(b"not-a-gif")


def test_catalog_tu_choi_url_github_khong_ghim_commit(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps([
            {
                "gif_id": "bad",
                "name": "Bad GIF",
                "url": "https://raw.githubusercontent.com/example/repo/main/bad.gif",
                "labels": ["laughter"],
                "aliases": ["bad"],
                "description": "Mô tả đủ dài cho một GIF không hợp lệ.",
                "quality": 0.5,
            }
        ]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="allowlist"):
        load_animated_catalog(path)


def test_preferred_style_animated_uu_tien_gif(tmp_path):
    settings = load_settings(env={}, root=tmp_path)
    opportunity = MemeOpportunity.model_validate({
        "segment_id": 1,
        "insert_meme": True,
        "confidence": 0.9,
        "trigger": "punchline",
        "reason": "Phản ứng cần chuyển động.",
        "emotion": "joy",
        "reaction_type": "laughing",
        "search_query": "laughing reaction",
        "preferred_style": "animated",
        "timing": {"anchor": 1, "delay": 0.15, "duration": 1.2},
    })
    candidates = [
        MemeCandidate(
            id="static",
            filename="static.png",
            type="image",
            style=["reaction"],
            semantic_score=1,
            quality=0.9,
        ),
        MemeCandidate(
            id="animated",
            filename="animated.gif",
            type="gif",
            style=["reaction", "animated"],
            semantic_score=1,
            quality=0.9,
        ),
    ]

    ranked = rank_memes(opportunity, candidates, settings.ranking)

    assert ranked[0].candidate.id == "animated"
    assert ranked[0].style_score == 1
