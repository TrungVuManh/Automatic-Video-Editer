from pathlib import Path

import pytest

from automeme.config import load_settings
from automeme.timeline.schema import (
    MemeEvent,
    Timeline,
    TimelineError,
    load_timeline,
    parse_timeline,
    save_timeline,
)
from automeme.timeline.validator import format_timeline_table, resolve_asset, validate_timeline

VALID = {
    "version": 1,
    "video": "wedding.mp4",
    "events": [{
        "id": "event_001", "type": "meme", "start": 8.88, "duration": 1.35,
        "asset": "assets/memes/awkward_smile.gif", "confidence": 0.91,
        "query": "man smiling awkwardly", "mode": "overlay",
        "position": "bottom-right", "scale": 0.30,
    }],
}


# ------------------------------------------------------------------ schema
def test_doc_duoc_vi_du_cua_spec():
    tl = parse_timeline(VALID)
    assert tl.version == 1 and tl.video == "wedding.mp4"
    e = tl.events[0]
    assert e.end == 10.23
    assert e.position == "bottom-right" and e.scale == 0.3


def test_vi_tri_va_co_co_the_bo_trong():
    tl = parse_timeline({"video": "a.mp4", "events": [
        {"id": "e1", "start": 1, "duration": 1, "asset": "x.png"}]})
    e = tl.events[0]
    assert e.position is None and e.scale is None and e.type == "meme" and e.mode == "overlay"


@pytest.mark.parametrize("sua, tu_khoa", [
    ({"start": -1}, "start"),
    ({"duration": 0}, "duration"),
    ({"scale": 2.0}, "scale"),
    ({"position": "giua"}, "position"),
    ({"type": "sfx"}, "type"),
    ({"confidence": 1.5}, "confidence"),
    ({"positon": "center"}, "positon"),  # gõ nhầm tên khóa
])
def test_bat_loi_tung_khoa_va_chi_ro_su_kien(sua, tu_khoa):
    data = {"video": "a.mp4", "events": [{**VALID["events"][0], **sua}]}
    with pytest.raises(TimelineError) as e:
        parse_timeline(data)
    assert tu_khoa in str(e.value)
    assert "sự kiện #0" in str(e.value)


def test_thieu_khoa_bat_buoc():
    with pytest.raises(TimelineError, match="asset"):
        parse_timeline({"video": "a.mp4", "events": [{"id": "e", "start": 1, "duration": 1}]})


def test_ghi_roi_doc_lai_khong_doi(tmp_path):
    tl = parse_timeline(VALID)
    path = save_timeline(tmp_path / "a.timeline.json", tl)
    assert load_timeline(path) == tl


def test_doc_file_hong(tmp_path):
    (tmp_path / "hong.json").write_text("{khong phai json", encoding="utf-8")
    with pytest.raises(TimelineError, match="JSON"):
        load_timeline(tmp_path / "hong.json")
    with pytest.raises(TimelineError, match="Không thấy timeline"):
        load_timeline(tmp_path / "khong_co.json")


def test_sap_xep_theo_thoi_gian():
    tl = parse_timeline({"video": "a.mp4", "events": [
        {"id": "b", "start": 5, "duration": 1, "asset": "x.png"},
        {"id": "a", "start": 1, "duration": 1, "asset": "x.png"}]})
    assert [e.id for e in tl.sorted_events()] == ["a", "b"]


# ------------------------------------------------------------------ validator
@pytest.fixture
def settings(tmp_path):
    return load_settings(env={}, root=tmp_path)


def _tl(*events) -> Timeline:
    return Timeline(video="a.mp4", events=[MemeEvent(**e) for e in events])


def _co_file(_: Path) -> bool:
    return True


def test_timeline_hop_le_khong_bao_gi():
    tl = _tl({"id": "e1", "start": 1, "duration": 1.5, "asset": "a.png"},
             {"id": "e2", "start": 12, "duration": 1.5, "asset": "b.png"})
    loi, canh_bao = validate_timeline(
        tl, video_duration=30,
        asset_paths={"a.png": Path("a.png"), "b.png": Path("b.png")}, ton_tai=_co_file)
    assert loi == [] and canh_bao == []


def test_bao_loi_khi_thieu_file_meme():
    tl = _tl({"id": "e1", "start": 1, "duration": 1, "asset": "thieu.png"})
    loi, _ = validate_timeline(tl, video_duration=10,
                               asset_paths={"thieu.png": Path("thieu.png")},
                               ton_tai=lambda p: False)
    assert any("không thấy file meme" in e for e in loi)


def test_bao_loi_khi_vuot_thoi_luong_video():
    tl = _tl({"id": "e1", "start": 9.5, "duration": 2, "asset": "a.png"})
    loi, _ = validate_timeline(tl, video_duration=10, asset_paths={"a.png": Path("a.png")},
                               ton_tai=_co_file)
    assert any("video chỉ dài" in e for e in loi)


def test_khong_biet_thoi_luong_thi_khong_kiem_tra():
    tl = _tl({"id": "e1", "start": 9.5, "duration": 2, "asset": "a.png"})
    loi, _ = validate_timeline(tl, video_duration=None, asset_paths={"a.png": Path("a.png")},
                               ton_tai=_co_file)
    assert loi == []


def test_bao_loi_khi_hai_meme_cung_vi_tri_trung_gio():
    tl = _tl({"id": "e1", "start": 1, "duration": 3, "asset": "a.png", "position": "center"},
             {"id": "e2", "start": 2, "duration": 3, "asset": "b.png", "position": "center"})
    loi, _ = validate_timeline(
        tl, video_duration=30,
        asset_paths={"a.png": Path("a.png"), "b.png": Path("b.png")}, ton_tai=_co_file)
    assert any("cùng vị trí và trùng thời gian" in e for e in loi)


def test_khac_vi_tri_thi_trung_gio_van_duoc():
    tl = _tl({"id": "e1", "start": 1, "duration": 3, "asset": "a.png", "position": "center"},
             {"id": "e2", "start": 2, "duration": 3, "asset": "b.png", "position": "top-left"})
    loi, _ = validate_timeline(
        tl, video_duration=30,
        asset_paths={"a.png": Path("a.png"), "b.png": Path("b.png")}, ton_tai=_co_file)
    assert loi == []


def test_bao_loi_trung_ma_su_kien():
    tl = _tl({"id": "e1", "start": 1, "duration": 1, "asset": "a.png"},
             {"id": "e1", "start": 12, "duration": 1, "asset": "a.png"})
    loi, _ = validate_timeline(tl, video_duration=30, asset_paths={"a.png": Path("a.png")},
                               ton_tai=_co_file)
    assert any("trùng mã sự kiện" in e for e in loi)


def test_canh_bao_cooldown_va_thoi_luong(settings):
    tl = _tl({"id": "e1", "start": 1, "duration": 5, "asset": "a.png", "position": "center"},
             {"id": "e2", "start": 7, "duration": 0.3, "asset": "a.png", "position": "top-left"})
    loi, canh_bao = validate_timeline(tl, video_duration=60,
                                      asset_paths={"a.png": Path("a.png")},
                                      meme_cfg=settings.meme, editing_cfg=settings.editing,
                                      ton_tai=_co_file)
    assert loi == []
    assert any("vượt mức tối đa" in c for c in canh_bao)         # 5s > duration_max
    assert any("ngắn hơn mức tối thiểu" in c for c in canh_bao)  # 0.3s < duration_min
    assert any("dưới cooldown" in c for c in canh_bao)           # cách nhau 1s < 7s


def test_canh_bao_mat_do(settings):
    tl = _tl(*[{"id": f"e{i}", "start": i * 2.0, "duration": 1.0, "asset": "a.png",
                "position": "center"} for i in range(10)])
    _, canh_bao = validate_timeline(tl, video_duration=30, asset_paths={"a.png": Path("a.png")},
                                    editing_cfg=settings.editing, ton_tai=_co_file)
    assert any("meme/phút" in c for c in canh_bao)


# ------------------------------------------------------------------ resolve + bảng
def test_resolve_asset_thu_goc_du_an_roi_den_assets(tmp_path):
    goc, assets = tmp_path, tmp_path / "assets"
    (assets / "memes").mkdir(parents=True)
    (assets / "memes" / "x.png").write_bytes(b"x")
    assert resolve_asset("assets/memes/x.png", goc, assets) == goc / "assets/memes/x.png"
    assert resolve_asset("memes/x.png", goc, assets) == assets / "memes/x.png"
    # không tồn tại ở đâu cả → trả về ứng viên đầu, để thông báo lỗi dễ hiểu
    assert resolve_asset("khong_co.png", goc, assets) == goc / "khong_co.png"


def test_resolve_asset_giu_nguyen_duong_dan_tuyet_doi(tmp_path):
    tuyet_doi = tmp_path / "ngoai" / "y.png"
    assert resolve_asset(str(tuyet_doi), tmp_path, tmp_path / "assets") == tuyet_doi


def test_bang_inspect_co_du_thong_tin():
    tl = parse_timeline(VALID)
    text = format_timeline_table(tl, [], ["meme hơi dày"], video_duration=47.8)
    assert "wedding.mp4" in text and "1 sự kiện" in text
    assert "event_001" in text and "00:08.88" in text and "bottom-right" in text and "30%" in text
    assert "[cảnh báo] meme hơi dày" in text
    assert "hợp lệ, render được." in text

    text_loi = format_timeline_table(tl, ["thiếu file"], [])
    assert "[LỖI]      thiếu file" in text_loi and "chưa render được" in text_loi
