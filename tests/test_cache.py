from automeme.cache import (
    artifact_status,
    file_fingerprint,
    manifest_path,
    record_artifact,
    stable_key,
)


def test_stable_key_khong_phu_thuoc_thu_tu_dict():
    assert stable_key({"a": 1, "b": 2}) == stable_key({"b": 2, "a": 1})
    assert stable_key({"a": 1}) != stable_key({"a": 2})


def test_file_fingerprint_doi_khi_dau_hoac_cuoi_doi(tmp_path):
    path = tmp_path / "large.bin"
    path.write_bytes(b"a" * (1024 * 1024 + 10))
    before = file_fingerprint(path)
    path.write_bytes(b"b" + b"a" * (1024 * 1024 + 8) + b"c")
    assert file_fingerprint(path) != before


def test_manifest_phan_biet_fresh_stale_modified_va_untracked(tmp_path):
    artifact = tmp_path / "analysis.json"
    artifact.write_text("{}", encoding="utf-8")
    manifest = manifest_path(tmp_path / "data", artifact, "analysis")

    assert artifact_status(
        artifact, manifest, stage="analysis", input_key="a",
    ) == "untracked"

    record_artifact(artifact, manifest, stage="analysis", input_key="a")
    assert artifact_status(
        artifact, manifest, stage="analysis", input_key="a",
    ) == "fresh"
    assert artifact_status(
        artifact, manifest, stage="analysis", input_key="b",
    ) == "stale"

    artifact.write_text('{"edited":true}', encoding="utf-8")
    assert artifact_status(
        artifact, manifest, stage="analysis", input_key="a",
    ) == "modified"


def test_manifest_hong_duoc_coi_la_untracked(tmp_path):
    artifact = tmp_path / "timeline.json"
    artifact.write_text("{}", encoding="utf-8")
    manifest = manifest_path(tmp_path / "data", artifact, "timeline")
    manifest.parent.mkdir(parents=True)
    manifest.write_text("not-json", encoding="utf-8")
    assert artifact_status(
        artifact, manifest, stage="timeline", input_key="key",
    ) == "untracked"


def test_artifact_chua_co_la_missing(tmp_path):
    artifact = tmp_path / "missing.mp4"
    manifest = manifest_path(tmp_path / "data", artifact, "render")
    assert artifact_status(
        artifact, manifest, stage="render", input_key="key",
    ) == "missing"
