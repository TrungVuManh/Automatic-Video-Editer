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
