from pathlib import Path

from automeme.analyzer.schema import Analysis, MemeOpportunity
from automeme.config import load_settings
from automeme.memes.base import MemeProvider, MemeProviderError
from automeme.memes.schema import MemeCandidate
from automeme.timeline.builder import build_timeline


def opportunity(segment_id, start, query="confused", confidence=0.9):
    return MemeOpportunity.model_validate({
        "segment_id": segment_id,
        "insert_meme": True,
        "confidence": confidence,
        "trigger": "punchline",
        "reason": "bất ngờ",
        "emotion": "confusion",
        "reaction_type": "confused reaction",
        "search_query": query,
        "preferred_style": "reaction",
        "timing": {"anchor": start - 0.15, "delay": 0.15, "duration": 1.5},
    })


def candidate(candidate_id, filename, score, *, emotion="confusion"):
    return MemeCandidate(
        id=candidate_id,
        filename=filename,
        type="image",
        tags=["reaction"],
        emotion=[emotion],
        style=["reaction"],
        semantic_score=score,
        quality=0.8,
    )


class Provider(MemeProvider):
    def __init__(self, results, *, broken=()):
        self.results = results
        self.broken = set(broken)
        self.queries = []

    def search(self, query, limit=10):
        self.queries.append((query, limit))
        return self.results.get(query, [])[:limit]

    def materialize(self, item):
        if item.id in self.broken:
            raise MemeProviderError("file hỏng")
        return Path(item.filename).resolve()


def analysis(*items):
    return Analysis(video="clip.mp4", backend="ollama", model="qwen", opportunities=list(items))


def test_builder_chon_meme_va_giu_thong_tin_de_duyet(tmp_path):
    asset = tmp_path / "assets" / "meme.png"
    asset.parent.mkdir()
    asset.write_bytes(b"PNG")
    provider = Provider({"confused": [candidate("a", str(asset), 0.9)]})
    settings = load_settings(env={}, root=tmp_path)

    timeline = build_timeline(
        analysis(opportunity(2, 3.15)), provider, settings.ranking,
        top_k=10, project_root=tmp_path, video_duration=10,
    )

    assert len(timeline.events) == 1
    event = timeline.events[0]
    assert event.id == "event_001" and event.start == 3.15 and event.duration == 1.5
    assert event.asset == "assets/meme.png"
    assert event.confidence == 0.9 and event.query == "confused" and event.reason == "bất ngờ"


def test_builder_thu_ung_vien_ke_tiep_neu_file_dau_hong(tmp_path):
    good = tmp_path / "good.png"
    good.write_bytes(b"PNG")
    provider = Provider({"confused": [
        candidate("broken", str(tmp_path / "broken.png"), 1),
        candidate("good", str(good), 0.8),
    ]}, broken={"broken"})
    settings = load_settings(env={}, root=tmp_path)
    timeline = build_timeline(analysis(opportunity(0, 1)), provider, settings.ranking,
                              top_k=10, project_root=tmp_path)
    assert timeline.events[0].asset == "good.png"


def test_builder_phat_meme_vua_dung_de_chon_anh_khac(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    same = candidate("same", str(a), 0.9)
    other = candidate("other", str(b), 0.8)
    provider = Provider({"q1": [same, other], "q2": [same, other]})
    settings = load_settings(env={}, root=tmp_path)
    timeline = build_timeline(
        analysis(opportunity(0, 1, "q1"), opportunity(1, 10, "q2")),
        provider,
        settings.ranking,
        top_k=10,
        project_root=tmp_path,
    )
    assert [event.asset for event in timeline.events] == ["a.png", "b.png"]


def test_builder_bo_co_hoi_khong_co_ung_vien_va_kep_cuoi_video(tmp_path):
    asset = tmp_path / "a.png"
    asset.write_bytes(b"a")
    provider = Provider({"none": [], "yes": [candidate("a", str(asset), 1)]})
    settings = load_settings(env={}, root=tmp_path)
    timeline = build_timeline(
        analysis(opportunity(0, 1, "none"), opportunity(1, 4.8, "yes")),
        provider,
        settings.ranking,
        top_k=10,
        project_root=tmp_path,
        video_duration=5,
    )
    assert len(timeline.events) == 1
    assert timeline.events[0].start == 4.8 and timeline.events[0].duration == 0.2


# ------------------------------------------------------------------ dựng kiểu chuyên nghiệp
from automeme.sfx.schema import SfxCandidate  # noqa: E402
from automeme.timeline.builder import pick_cutaways, prefer_animated, punch_zoom  # noqa: E402
from automeme.timeline.schema import MemeEvent, SfxEvent, ZoomEvent  # noqa: E402


def _pro(tmp_path):
    return load_settings("pro", env={}, root=tmp_path)


def test_chon_cat_tran_man_hinh_tu_tin_nhat_va_cach_xa(tmp_path):
    cfg = _pro(tmp_path).cutaway  # tối đa 2/phút, cooldown 15 s, confidence ≥ 0.8
    items = [opportunity(0, 5, confidence=0.85), opportunity(1, 10, confidence=0.95),
             opportunity(2, 30, confidence=0.9), opportunity(3, 40, confidence=0.7)]
    # 60 s → tối đa 2; chọn 10 s (0.95) rồi 30 s (0.9); 5 s quá gần 10 s; 40 s dưới ngưỡng
    assert pick_cutaways(items, cfg, 60) == {1, 2}
    assert pick_cutaways(items, cfg, 20) == {1}  # video 20 s → tối đa 1
    tat = cfg.model_copy(update={"mode": "never"})
    assert pick_cutaways(items, tat, 60) == set()


def test_uu_tien_gif_khi_diem_gan_bang(tmp_path):
    from automeme.memes.ranker import RankedMeme

    def ranked(cid, kind, score):
        c = candidate(cid, f"{cid}.x", 0.9).model_copy(update={"type": kind})
        return RankedMeme(c, score, 0.9, 0, 0, 0.8, 1)

    anh, gif_gan, gif_xa = ranked("anh", "image", 0.80), ranked("g1", "gif", 0.75), \
        ranked("g2", "gif", 0.60)
    assert [r.candidate.id for r in prefer_animated([anh, gif_gan])] == ["g1", "anh"]
    assert [r.candidate.id for r in prefer_animated([anh, gif_xa])] == ["anh", "g2"]


def test_zoom_truoc_cu_cat(tmp_path):
    cfg = _pro(tmp_path).cutaway
    z = punch_zoom(10.0, cfg, "event_001")
    assert (z.start, z.duration, z.factor) == (9.7, 0.4, 1.1)  # kéo qua lúc cắt 0.1 s
    assert punch_zoom(0.02, cfg, "e") is None  # cắt ngay đầu video: không có chỗ zoom


class SoundProvider:
    def __init__(self, sounds, asset):
        self.sounds, self.asset, self.queries = sounds, asset, []

    def search(self, query, _limit=10):
        self.queries.append(query)
        return [s.model_copy(update={"semantic_score": 1.0}) for s in self.sounds]

    def materialize(self, _item):
        return self.asset


def _am(sid):
    return SfxCandidate(id=sid, filename=f"{sid}.ogg", tags=["impact"], duration=0.5,
                        recommended_volume=0.8)


def test_builder_pro_cat_tran_man_hinh_kem_zoom_va_sfx_khong_lap(tmp_path):
    settings = _pro(tmp_path)
    gif = tmp_path / "assets" / "g.gif"
    gif.parent.mkdir()
    gif.write_bytes(b"GIF")
    hinh = candidate("g", str(gif), 0.9).model_copy(update={"type": "gif"})
    provider = Provider({"confused": [hinh]})
    sound_asset = tmp_path / "boom.ogg"
    sound_asset.write_bytes(b"OggS")
    sounds = SoundProvider([_am("boom1"), _am("boom2")], sound_asset)

    # hai khoảnh khắc đủ mạnh, cách nhau 20 s, AI không đề xuất SFX nào
    timeline = build_timeline(
        analysis(opportunity(0, 10, confidence=0.95), opportunity(1, 30, confidence=0.9)),
        provider, settings.ranking, top_k=10, project_root=tmp_path, video_duration=60,
        sfx_provider=sounds, sfx_settings=settings.sfx,
        cutaway_settings=settings.cutaway, meme_settings=settings.meme,
    )
    kinds = [(type(e).__name__, getattr(e, "mode", None)) for e in timeline.sorted_events()]
    assert kinds == [("ZoomEvent", None), ("MemeEvent", "cutaway"), ("SfxEvent", None),
                     ("ZoomEvent", None), ("MemeEvent", "cutaway"), ("SfxEvent", None)]
    cuts = [e for e in timeline.events if isinstance(e, MemeEvent)]
    assert all(0.8 <= e.duration <= 1.3 for e in cuts)  # cắt ngắn theo cấu hình
    sfx = [e for e in timeline.events if isinstance(e, SfxEvent)]
    assert [s.query for s in sfx] == ["impact", "impact"]  # SFX mặc định khi AI không đề xuất
    assert sounds.queries == ["impact", "impact"]  # mỗi cú cắt tìm SFX riêng


def test_sfx_khong_lap_cung_file_trong_cua_so_gan_day(tmp_path):
    settings = _pro(tmp_path)
    sound_asset = tmp_path / "boom.ogg"
    sound_asset.write_bytes(b"OggS")

    class ProviderTheoId(SoundProvider):
        def materialize(self, item):
            return tmp_path / f"{item.id}.ogg"

    for sid in ("boom1", "boom2"):
        (tmp_path / f"{sid}.ogg").write_bytes(b"OggS")
    items = []
    for seg, t in ((0, 10), (1, 25), (2, 40)):
        o = opportunity(seg, t, confidence=0.9).model_copy(update={
            "insert_meme": False, "insert_sfx": True, "sfx_query": "impact"})
        items.append(o)
    timeline = build_timeline(
        analysis(*items), Provider({}), settings.ranking, top_k=10, project_root=tmp_path,
        video_duration=60, sfx_provider=ProviderTheoId([_am("boom1"), _am("boom2")], None),
        sfx_settings=settings.sfx.model_copy(update={"cooldown": 5, "max_per_minute": 5}),
    )
    assets = [e.asset for e in timeline.sorted_events()]
    assert assets == ["boom1.ogg", "boom2.ogg"]  # âm thứ 3 bị bỏ vì cả hai file đều vừa dùng


def test_bo_template_can_chu_va_luan_phien_vi_tri(tmp_path):
    settings = _pro(tmp_path)
    tpl = tmp_path / "tpl.png"
    tpl.write_bytes(b"PNG")
    ok = tmp_path / "ok.png"
    ok.write_bytes(b"PNG")
    template = candidate("tpl", str(tpl), 0.99).model_copy(update={"style": ["dialogue"]})
    reaction = candidate("ok", str(ok), 0.7)
    provider = Provider({"confused": [template, reaction]})
    items = [opportunity(i, 10 + i * 10, confidence=0.7) for i in range(3)]  # dưới ngưỡng cắt
    timeline = build_timeline(
        analysis(*items), provider, settings.ranking, top_k=10, project_root=tmp_path,
        video_duration=60, cutaway_settings=settings.cutaway, meme_settings=settings.meme,
    )
    memes = [e for e in timeline.events if isinstance(e, MemeEvent)]
    assert {e.asset for e in memes} == {"ok.png"}  # template "dialogue" không được chọn
    assert [e.position for e in memes] == ["top-right", "bottom-right", "top-right"]
    assert all(e.mode == "overlay" for e in memes)
    assert not any(isinstance(e, ZoomEvent) for e in timeline.events)
