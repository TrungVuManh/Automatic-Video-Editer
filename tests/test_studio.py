import http.client
import io
import json
import threading
import time

import pytest

from automeme.config import load_settings
from automeme.studio.server import STATIC_DIR, create_studio_server
from automeme.studio.service import JobRequest, MetadataPatch, StudioError, StudioService


@pytest.fixture
def studio(tmp_path):
    settings = load_settings(env={}, root=tmp_path)
    (settings.paths.data_dir / "input").mkdir(parents=True)
    profiles = tmp_path / "configs"
    profiles.mkdir()
    (profiles / "default.yaml").write_text("{}", encoding="utf-8")

    def runner(video, active, force, progress):
        assert active is settings
        progress("transcribe", "running")
        progress("transcribe", "completed")
        progress("analyze", "running")
        progress("analyze", "completed")
        progress("timeline", "running")
        progress("timeline", "completed")
        progress("render", "running")
        output = active.paths.data_dir / "output" / f"{video.stem}_automeme.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"done")
        progress("render", "completed")
        return output, object()

    return StudioService(
        settings,
        settings_loader=lambda _profile: settings,
        runner=runner,
        profiles_dir=profiles,
        environment_checker=lambda _settings: [
            ("Python", "ok", "3.11"),
            ("Ollama", "warn", "chưa chạy"),
        ],
    )


def test_upload_video_an_toan_atomic_va_khong_ghi_de(studio):
    first = studio.upload_video("Video Demo.MP4", io.BytesIO(b"abc"), 3)
    second = studio.upload_video("Video Demo.MP4", io.BytesIO(b"xyz"), 3)

    assert first["name"] == "video-demo.mp4"
    assert second["name"] == "video-demo-2.mp4"
    assert [row["status"] for row in studio.projects()] == ["new", "new"]
    assert not list((studio.settings.paths.data_dir / "input").glob("*.part"))


@pytest.mark.parametrize("name", ["../secret.mp4", "secret.exe", "", "C:/secret.mp4"])
def test_upload_video_chan_ten_va_duoi_nguy_hiem(studio, name):
    with pytest.raises(StudioError):
        studio.upload_video(name, io.BytesIO(b"x"), 1)


def test_upload_thieu_du_lieu_xoa_file_tam(studio):
    with pytest.raises(StudioError, match="bị thiếu"):
        studio.upload_video("clip.mp4", io.BytesIO(b"x"), 2)
    assert not list(studio.settings.paths.data_dir.rglob("*.part"))


def test_kho_meme_upload_va_cap_nhat_metadata_giu_dong_hong(studio):
    library = studio.settings.meme.library_file
    library.parent.mkdir(parents=True, exist_ok=True)
    library.write_text("# ghi chú\n{khong hop le}\n", encoding="utf-8")
    item = studio.upload_asset("Reaction WOW.PNG", io.BytesIO(b"png"), 3)

    updated = studio.update_metadata(
        item.id,
        MetadataPatch(
            id=item.id,
            tags=["wow", "reaction"],
            emotion=["shock"],
            description="Bất ngờ mạnh",
            quality=0.9,
        ),
    )

    assert updated.quality == 0.9 and updated.tags == ["wow", "reaction"]
    assert studio.library_asset(item.id).read_bytes() == b"png"
    text = library.read_text(encoding="utf-8")
    assert "# ghi chú" in text and "{khong hop le}" in text


def test_kho_meme_khong_phat_file_ngoai_thu_muc_assets(studio, tmp_path):
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"secret")
    library = studio.settings.meme.library_file
    library.parent.mkdir(parents=True, exist_ok=True)
    library.write_text(json.dumps({
        "id": "outside",
        "filename": str(outside),
        "type": "image",
    }) + "\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        studio.library_asset("outside")


def test_job_bao_tien_do_va_chan_chay_song_song(studio):
    studio.upload_video("clip.mp4", io.BytesIO(b"abc"), 3)
    state = studio.start_job(JobRequest(video="clip.mp4", profile="default"))
    assert state["video"] == "clip.mp4"
    deadline = time.time() + 2
    while studio.job()["status"] not in {"completed", "failed"} and time.time() < deadline:
        time.sleep(0.01)
    final = studio.job()
    assert final["status"] == "completed"
    assert final["completed_stages"] == ["transcribe", "analyze", "timeline", "render"]
    assert final["output"].endswith("clip_automeme.mp4")


def test_dashboard_co_du_du_an_profile_moi_truong(studio):
    studio.upload_video("clip.mp4", io.BytesIO(b"abc"), 3)
    dashboard = studio.dashboard()
    assert dashboard["project_count"] == 1
    assert dashboard["profiles"] == ["default"]
    assert dashboard["environment"][1]["status"] == "warn"


def test_static_ui_co_cac_man_hinh_va_open_source():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert "AutoMeme Studio" in html
    for view in ("view-home", "view-create", "view-editor", "view-library", "view-settings"):
        assert view in html
    for library in ("Plyr", "FilePond", "Sortable", "WaveSurfer"):
        assert library in html + js
    assert (STATIC_DIR / "vendor" / "licenses" / "wavesurfer.js.txt").is_file()


def test_studio_server_auth_upload_dashboard_va_job(studio):
    server = create_studio_server(studio, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    try:
        connection.request("GET", "/")
        response = connection.getresponse()
        assert response.status == 200
        assert "__AUTOMEME_TOKEN__" not in response.read().decode("utf-8")
        cookie = response.getheader("Set-Cookie").split(";", 1)[0]

        connection.request("GET", "/api/dashboard")
        forbidden = connection.getresponse()
        assert forbidden.status == 403
        forbidden.read()

        body = b"video"
        connection.request("POST", "/api/videos/upload", body=body, headers={
            "X-Automeme-Token": server.session_token,
            "X-Filename": "demo.mp4",
            "Content-Length": str(len(body)),
        })
        uploaded = connection.getresponse()
        assert uploaded.status == 201
        assert json.loads(uploaded.read())["project"]["name"] == "demo.mp4"

        connection.request("GET", "/media/video?video=demo.mp4", headers={
            "Cookie": cookie,
            "Range": "bytes=1-3",
        })
        media = connection.getresponse()
        assert media.status == 206 and media.read() == b"ide"

        connection.request("GET", "/api/dashboard", headers={"Cookie": cookie})
        dashboard = connection.getresponse()
        assert dashboard.status == 200
        assert json.loads(dashboard.read())["project_count"] == 1

        job_body = json.dumps({"video": "demo.mp4", "profile": "default"}).encode()
        connection.request("POST", "/api/jobs", body=job_body, headers={
            "X-Automeme-Token": server.session_token,
            "Content-Type": "application/json",
            "Content-Length": str(len(job_body)),
        })
        assert connection.getresponse().status == 202
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_studio_server_tu_choi_bind_ra_mang(studio):
    from automeme.studio.server import StudioHTTPServer

    with pytest.raises(ValueError, match="loopback"):
        StudioHTTPServer(("0.0.0.0", 0), studio)
