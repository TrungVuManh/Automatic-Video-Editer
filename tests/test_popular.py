import json

from automeme.config import load_settings
from automeme.memes.local import LocalMemeProvider, parse_library
from automeme.memes.popular import (
    InstallResult,
    install_popular_memes,
    load_popular_catalog,
)


class FakeResponse:
    status_code = 200
    headers = {"content-type": "image/jpeg", "content-length": "8"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def raise_for_status(self):
        return None

    def iter_bytes(self):
        yield b"fake-img"


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


def test_catalog_co_dung_100_meme_va_nhan_hop_le():
    catalog = load_popular_catalog()
    assert len(catalog) == 100
    assert len({item.template_id for item in catalog}) == 100
    assert sum(not item.safe for item in catalog) == 3
    assert all(item.labels and item.description and item.aliases for item in catalog)


def test_cai_100_meme_ghi_file_metadata_va_tai_su_dung(tmp_path):
    settings = load_settings(env={}, root=tmp_path)
    client = FakeClient()

    first = install_popular_memes(
        settings,
        client_factory=lambda **_kwargs: client,
    )
    second = install_popular_memes(
        settings,
        client_factory=lambda **_kwargs: FakeClient(),
    )

    assert first == InstallResult(total=100, installed=100, reused=0, failed=0, errors=[])
    assert second.installed == 0 and second.reused == 100 and second.failed == 0
    assert client.closed and len(client.urls) == 100
    items, warnings = parse_library(
        settings.meme.library_file.read_text(encoding="utf-8")
    )
    assert not warnings and len(items) == 100
    assert all(item.source_url and item.license_note for item in items)
    assert len(list((settings.paths.assets_dir / "memes" / "popular").iterdir())) == 100


def test_nhan_song_ngu_giup_tim_dung_ngu_canh(tmp_path):
    settings = load_settings(env={}, root=tmp_path)
    install_popular_memes(
        settings,
        client_factory=lambda **_kwargs: FakeClient(),
    )
    provider = LocalMemeProvider(
        library_file=settings.meme.library_file,
        asset_dirs=[settings.paths.assets_dir / "memes"],
        project_root=tmp_path,
    )

    scenarios = {
        "kế hoạch thất bại phản tác dụng": "popular-imgflip-131940431",
        "ngượng ngùng awkward silence": "popular-imgflip-148909805",
        "tự gây ra rồi đổ lỗi": "popular-imgflip-79132341",
        "nâng ly chúc mừng tuyệt vời": "popular-imgflip-5496396",
        "chờ mãi quá lâu": "popular-imgflip-4087833",
    }
    for query, expected in scenarios.items():
        ids = {item.id for item in provider.search(query, limit=10)}
        assert expected in ids, (query, ids)


def test_meme_nhay_cam_khong_duoc_tim_tu_dong(tmp_path):
    settings = load_settings(env={}, root=tmp_path)
    install_popular_memes(
        settings,
        client_factory=lambda **_kwargs: FakeClient(),
    )
    provider = LocalMemeProvider(
        library_file=settings.meme.library_file,
        asset_dirs=[settings.paths.assets_dir / "memes"],
        project_root=tmp_path,
    )
    unsafe = {
        "popular-imgflip-208915813",
        "popular-imgflip-247113703",
        "popular-imgflip-135678846",
    }
    assert not (unsafe & {item.id for item in provider.search("danger thảm kịch", limit=100)})


def test_catalog_tu_choi_label_khong_co_trong_ontology(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([{
        "template_id": "1",
        "name": "Bad",
        "url": "https://i.imgflip.com/a.jpg",
        "labels": ["khong-ton-tai"],
        "aliases": ["bad"],
        "description": "Mô tả đủ dài để hợp lệ.",
        "quality": 0.5,
    }]), encoding="utf-8")
    try:
        load_popular_catalog(path)
    except ValueError as exc:
        assert "chưa định nghĩa" in str(exc)
    else:
        raise AssertionError("Catalog label lạ phải bị từ chối")
