import json
from pathlib import Path

import pytest

from automeme.analyzer.schema import MemeOpportunity
from automeme.config import load_settings
from automeme.memes.base import MemeProvider, MemeProviderError
from automeme.memes.factory import create_meme_provider
from automeme.memes.local import LocalMemeProvider, local_semantic_score, parse_library
from automeme.memes.meme_search import FallbackMemeProvider, MemeSearchProvider
from automeme.memes.ranker import rank_memes
from automeme.memes.schema import MemeCandidate


def candidate(**changes):
    data = {
        "id": "confused",
        "filename": "assets/memes/confused.gif",
        "type": "gif",
        "tags": ["confused", "reaction"],
        "emotion": ["confusion"],
        "style": ["reaction"],
        "description": "confused person reaction",
        "quality": 0.8,
        "semantic_score": 0.9,
    }
    return MemeCandidate.model_validate({**data, **changes})


def opportunity(**changes):
    data = {
        "segment_id": 0,
        "insert_meme": True,
        "confidence": 0.9,
        "trigger": "unexpected answer",
        "reason": "bất ngờ",
        "emotion": "confusion",
        "reaction_type": "confused reaction",
        "search_query": "confused person reaction",
        "preferred_style": "reaction",
        "timing": {"anchor": 2, "delay": 0.15, "duration": 1.5},
    }
    return MemeOpportunity.model_validate({**data, **changes})


def test_parse_library_bo_rieng_dong_hong_va_bat_khoa_la():
    good = candidate().model_dump_json()
    typo = json.dumps({**candidate(id="typo").model_dump(), "quailty": 1})
    items, warnings = parse_library(f"# ghi chú\n{good}\nkhông-json\n{typo}\n{good}")
    assert [item.id for item in items] == ["confused"]
    assert len(warnings) == 3
    assert "dòng 3" in warnings[0] and "quailty" in warnings[1] and "trùng id" in warnings[2]


def test_local_search_doc_metadata_va_bo_meme_khong_an_toan(tmp_path):
    assets = tmp_path / "assets" / "memes"
    assets.mkdir(parents=True)
    (assets / "confused.gif").write_bytes(b"GIF")
    (assets / "unsafe.png").write_bytes(b"PNG")
    library = assets / "library.jsonl"
    library.write_text("\n".join([
        candidate().model_dump_json(exclude={"semantic_score"}),
        candidate(id="unsafe", filename="assets/memes/unsafe.png", type="image",
                  safe=False).model_dump_json(exclude={"semantic_score"}),
    ]), encoding="utf-8")
    provider = LocalMemeProvider(library_file=library, asset_dirs=[assets],
                                 project_root=tmp_path)
    found = provider.search("confused reaction", 10)
    assert [item.id for item in found] == ["confused"]
    assert found[0].semantic_score > 0
    assert provider.materialize(found[0]) == (assets / "confused.gif").resolve()


def test_local_tu_quet_file_chua_co_metadata(tmp_path):
    assets = tmp_path / "assets" / "memes"
    assets.mkdir(parents=True)
    (assets / "shocked-cat.png").write_bytes(b"PNG")
    provider = LocalMemeProvider(library_file=assets / "missing.jsonl", asset_dirs=[assets],
                                 project_root=tmp_path)
    found = provider.search("shocked cat", 10)
    assert len(found) == 1 and found[0].type == "image"
    assert found[0].filename == "assets/memes/shocked-cat.png"


def test_local_score_khong_match_thi_bang_khong():
    assert local_semantic_score("celebrating success", candidate()) == 0


def test_ranker_dung_trong_so_va_phat_trung():
    settings = load_settings(env={}).ranking
    fresh = candidate(id="fresh", usage_count=0)
    used = candidate(id="used", usage_count=0)
    ranked = rank_memes(opportunity(), [used, fresh], settings, recent_ids={"used"})
    assert ranked[0].candidate.id == "fresh"
    assert ranked[0].score - ranked[1].score == pytest.approx(settings.duplicate_penalty)
    assert ranked[0].emotion_score == 1 and ranked[0].style_score == 1


class FakeResponse:
    def __init__(self, *, data=None, body=None, status=200, headers=None):
        self._data = data
        self._body = body or []
        self.status_code = status
        self.headers = headers or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_bytes(self):
        return iter(self._body)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeClient:
    def __init__(self, *, search_response=None, stream_response=None, captured=None, **kwargs):
        self.search_response = search_response
        self.stream_response = stream_response
        self.captured = captured if captured is not None else {}
        self.captured["init"] = kwargs

    def get(self, path, **kwargs):
        self.captured["get"] = (path, kwargs)
        return self.search_response

    def stream(self, method, url):
        self.captured["stream"] = (method, url)
        return self.stream_response

    def close(self):
        self.captured["closed"] = True


def test_meme_search_dung_api_v1_vector_va_ignore_field_moi(tmp_path):
    captured = {}
    response = FakeResponse(data={"data": [{
        "id": 42,
        "filename": "ship-it.gif",
        "description": "celebration reaction",
        "tags": ["reaction", "work"],
        "media_type": "image/gif",
        "content_url": "/api/v1/memes/42/content",
        "future_field": True,
    }]})

    def factory(**kwargs):
        return FakeClient(search_response=response, captured=captured, **kwargs)

    provider = MemeSearchProvider(base_url="http://127.0.0.1:3000", token="secret",
                                  cache_dir=tmp_path, client_factory=factory)
    found = provider.search("ship it", 30)
    assert found[0].id == "meme-search-42" and found[0].type == "gif"
    assert captured["get"][0] == "/api/v1/search"
    assert captured["get"][1]["params"]["mode"] == "vector"
    assert captured["get"][1]["params"]["limit"] == 20
    assert captured["init"]["headers"] == {"Authorization": "Bearer secret"}


def test_meme_search_tai_atomic_va_dung_cache(tmp_path):
    captured = {}
    response = FakeResponse(body=[b"GIF", b"89a"], headers={"content-length": "6"})

    def factory(**kwargs):
        return FakeClient(stream_response=response, captured=captured, **kwargs)

    provider = MemeSearchProvider(base_url="http://127.0.0.1:3000", token="secret",
                                  cache_dir=tmp_path, client_factory=factory)
    remote = candidate(id="meme-search-42", filename="ship it.gif", source="meme-search",
                       content_url="/api/v1/memes/42/content")
    path = provider.materialize(remote)
    assert path.read_bytes() == b"GIF89a"
    assert not list(tmp_path.glob("*.part"))
    assert provider.materialize(remote) == path


def test_meme_search_chan_origin_khac_va_file_qua_lon(tmp_path):
    provider = MemeSearchProvider(base_url="http://127.0.0.1:3000", token="secret",
                                  cache_dir=tmp_path, client_factory=lambda **kw: None,
                                  max_download_mb=0.000001)
    evil = candidate(source="meme-search", content_url="https://evil.test/x")
    with pytest.raises(MemeProviderError, match="origin khác"):
        provider.materialize(evil)

    response = FakeResponse(body=[b"too big"])
    provider._client_factory = lambda **kw: FakeClient(stream_response=response, **kw)
    large = candidate(source="meme-search", content_url="/api/v1/memes/1/content")
    with pytest.raises(MemeProviderError, match="vượt giới hạn"):
        provider.materialize(large)
    assert not list(tmp_path.glob("*.part"))


def test_meme_search_khong_theo_redirect(tmp_path):
    response = FakeResponse(status=302)
    provider = MemeSearchProvider(
        base_url="http://127.0.0.1:3000",
        token="secret",
        cache_dir=tmp_path,
        client_factory=lambda **kw: FakeClient(stream_response=response, **kw),
    )
    remote = candidate(source="meme-search", content_url="/api/v1/memes/1/content")
    with pytest.raises(MemeProviderError, match="redirect"):
        provider.materialize(remote)


class StaticProvider(MemeProvider):
    def __init__(self, result=None, error=None):
        self.result = result or []
        self.error = error

    def search(self, query, limit=10):
        if self.error:
            raise self.error
        return self.result[:limit]

    def materialize(self, item):
        return Path(item.filename)


def test_fallback_khi_api_hong():
    fallback = StaticProvider([candidate(id="local")])
    provider = FallbackMemeProvider(
        StaticProvider(error=MemeProviderError("API hỏng")), fallback,
    )
    assert [item.id for item in provider.search("x")] == ["local"]


def test_factory_khong_token_thi_chi_dung_local(tmp_path):
    settings = load_settings(env={}, root=tmp_path)
    assert isinstance(create_meme_provider(settings), LocalMemeProvider)
