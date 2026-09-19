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
    assert "popular-library-button" in html
    assert "/api/library/popular?limit=100" in js
    assert "animated-library-button" in html
    assert "/api/library/animated?limit=30" in js
    assert "sfx-library-button" in html
    assert "/api/library/sfx?limit=30" in js
    for element in ("youtube-url", "youtube-from", "youtube-to", "youtube-download"):
        assert f'id="{element}"' in html
    assert "/api/videos/youtube" in js
    # hiệu ứng khi job xong chỉ chạy một lần — chặn vòng lặp updateJob ↔ loadDashboard
    assert "state.handledJob===key" in js and "updateJob(data.job,{silent:true})" in js
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


def test_studio_server_cai_kho_meme_pho_bien(studio, monkeypatch):
    monkeypatch.setattr(
        studio,
        "install_popular_library",
        lambda *, limit: {
            "total": limit,
            "installed": limit,
            "reused": 0,
            "failed": 0,
            "errors": [],
        },
    )
    server = create_studio_server(studio, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    try:
        connection.request(
            "POST",
            "/api/library/popular?limit=100",
            headers={"X-Automeme-Token": server.session_token},
        )
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read()) == {
            "ok": True,
            "total": 100,
            "installed": 100,
            "reused": 0,
            "failed": 0,
            "errors": [],
        }
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_studio_server_cai_kho_gif_dong(studio, monkeypatch):
    monkeypatch.setattr(
        studio,
        "install_animated_library",
        lambda *, limit: {
            "total": limit,
            "installed": limit,
            "reused": 0,
            "failed": 0,
            "errors": [],
        },
    )
    server = create_studio_server(studio, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    try:
        connection.request(
            "POST",
            "/api/library/animated?limit=30",
            headers={"X-Automeme-Token": server.session_token},
        )
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["installed"] == 30
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_studio_server_tu_choi_bind_ra_mang(studio):
    from automeme.studio.server import StudioHTTPServer

    with pytest.raises(ValueError, match="loopback"):
        StudioHTTPServer(("0.0.0.0", 0), studio)


# ------------------------------------------------------------------ tải YouTube
def _studio_tai(tmp_path, downloader):
    from automeme.studio.service import StudioService

    settings = load_settings(env={}, root=tmp_path)
    (settings.paths.data_dir / "input").mkdir(parents=True)
    return StudioService(settings, settings_loader=lambda _p: settings,
                         runner=lambda *a: pytest.fail("không được chạy pipeline"),
                         environment_checker=lambda _s: [], downloader=downloader)


def _cho_xong(studio, han=3.0):
    deadline = time.time() + han
    while studio.job()["status"] not in {"completed", "failed"} and time.time() < deadline:
        time.sleep(0.01)
    return studio.job()


def _tai_gia(request, settings, progress):
    from automeme.media.youtube import DownloadResult

    progress(None, "Đang đọc thông tin video")
    progress(40.0, "Đang tải hình: 40%")
    path = settings.paths.data_dir / "input" / "phim-aqz-KE-bpKQ-0s-30s.mp4"
    path.write_bytes(b"mp4")
    path.with_name(path.stem + ".source.json").write_text("{}", encoding="utf-8")
    return DownloadResult(path=path, source={}, skipped=False)


def test_tai_youtube_chay_nen_va_video_hien_trong_du_an(tmp_path):
    from automeme.studio.service import DownloadRequest

    studio = _studio_tai(tmp_path, _tai_gia)
    state = studio.start_download(DownloadRequest(url="https://youtu.be/aqz-KE-bpKQ",
                                                  start="0", end="30"))
    assert state["kind"] == "download" and state["video"] == "YouTube aqz-KE-bpKQ"
    final = _cho_xong(studio)
    assert final["status"] == "completed", final
    assert final["video"] == "phim-aqz-KE-bpKQ-0s-30s.mp4" and final["percent"] == 100.0
    assert "Đã tải xong" in final["message"]
    # file .source.json đi kèm không được hiện thành một dự án
    assert [row["name"] for row in studio.projects()] == ["phim-aqz-KE-bpKQ-0s-30s.mp4"]


def test_tai_youtube_link_sai_bao_ngay_khong_tao_job(tmp_path):
    from automeme.studio.service import DownloadRequest

    studio = _studio_tai(tmp_path, lambda *a: pytest.fail("không được tải"))
    with pytest.raises(StudioError, match="Chỉ hỗ trợ link YouTube"):
        studio.start_download(DownloadRequest(url="http://192.168.1.1/admin"))
    assert studio.job() is None


def test_tai_youtube_loi_hien_trong_job(tmp_path):
    from automeme.media.youtube import DownloadError
    from automeme.studio.service import DownloadRequest

    def hong(request, settings, progress):
        raise DownloadError("Video ở chế độ riêng tư — không tải được.")

    studio = _studio_tai(tmp_path, hong)
    studio.start_download(DownloadRequest(url="https://youtu.be/aqz-KE-bpKQ"))
    final = _cho_xong(studio)
    assert final["status"] == "failed" and "riêng tư" in final["error"]


def test_tai_youtube_dung_chung_hang_doi_voi_pipeline(tmp_path):
    from automeme.studio.service import DownloadRequest

    cho = threading.Event()

    def tai_cham(request, settings, progress):
        cho.wait(3)
        return _tai_gia(request, settings, progress)

    studio = _studio_tai(tmp_path, tai_cham)
    studio.start_download(DownloadRequest(url="https://youtu.be/aqz-KE-bpKQ"))
    with pytest.raises(StudioError, match="Hãy chờ"):
        studio.start_download(DownloadRequest(url="https://youtu.be/aqz-KE-bpKQ"))
    cho.set()
    assert _cho_xong(studio)["status"] == "completed"


def test_studio_server_endpoint_tai_youtube(tmp_path):
    studio = _studio_tai(tmp_path, _tai_gia)
    server = create_studio_server(studio, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)

    def post(body):
        data = json.dumps(body).encode()
        connection.request("POST", "/api/videos/youtube", body=data, headers={
            "X-Automeme-Token": server.session_token, "Content-Type": "application/json",
            "Content-Length": str(len(data)),
        })
        response = connection.getresponse()
        return response.status, json.loads(response.read())

    try:
        status, data = post({"url": "https://vimeo.com/123"})
        assert status == 400 and "Chỉ hỗ trợ link YouTube" in data["error"]
        status, data = post({"url": "https://youtu.be/aqz-KE-bpKQ", "cookies": "x"})
        assert status == 400  # khóa lạ bị từ chối
        status, data = post({"url": "https://youtu.be/aqz-KE-bpKQ", "start": "0", "end": "30"})
        assert status == 202 and data["job"]["kind"] == "download"
        assert _cho_xong(studio)["status"] == "completed"
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_studio_server_goi_y_thay_meme_them_meme_va_zoom(studio):
    """Người duyệt tự quyết meme: xem gợi ý + xem trước, đổi sang tràn màn hình, thêm meme,
    chỉnh zoom; zoom không có file xem trước."""
    from automeme.review.service import ReviewSession
    from automeme.timeline.schema import MemeEvent, Timeline, ZoomEvent, save_timeline

    settings = studio.settings
    root = settings.paths.assets_dir.parent
    memes = settings.paths.assets_dir / "memes"
    memes.mkdir(parents=True)
    (memes / "a.png").write_bytes(b"PNG-A")
    (memes / "b.gif").write_bytes(b"GIF-B")
    (root / "clip.mp4").write_bytes(b"video")
    settings.meme.library_file.write_text(
        '{"id": "soc", "filename": "assets/memes/b.gif", "type": "gif", '
        '"description": "shocked reaction"}\n', encoding="utf-8")
    timeline_path = settings.paths.data_dir / "timelines" / "clip.timeline.json"
    save_timeline(timeline_path, Timeline(video="clip.mp4", events=[
        ZoomEvent(id="event_001", start=0.7, duration=0.4),
        MemeEvent(id="event_002", start=1, duration=1, asset="assets/memes/a.png",
                  query="shocked"),
    ]))
    studio._reviews["clip.mp4"] = ReviewSession(
        video=root / "clip.mp4", timeline_path=timeline_path, settings=settings,
        output=root / "out.mp4", video_duration=30,
    )
    server = create_studio_server(studio, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    token = {"X-Automeme-Token": server.session_token}

    def get(path):
        connection.request("GET", path, headers=token)
        response = connection.getresponse()
        return response.status, response.read()

    def post(path, payload):
        body = json.dumps(payload).encode()
        connection.request("POST", path, body=body, headers={
            **token, "Content-Type": "application/json", "Content-Length": str(len(body))})
        response = connection.getresponse()
        return response.status, json.loads(response.read())

    try:
        status, body = get("/api/project?video=clip.mp4")
        events = {e["id"]: e for e in json.loads(body)["events"]}
        assert status == 200 and "preview_url" not in events["event_001"]
        assert "preview_url" in events["event_002"]

        status, body = get("/api/suggestions?video=clip.mp4&id=event_002")
        items = json.loads(body)["items"]
        assert status == 200 and items[0]["asset"] == "assets/memes/b.gif"
        assert get(items[0]["preview_url"]) == (200, b"GIF-B")
        assert get("/media/asset-file?video=clip.mp4&path=..%2F..%2Fsecret.txt")[0] == 404
        assert get("/api/suggestions?video=clip.mp4&id=event_001")[0] == 404  # zoom

        status, data = post("/api/events/event_002/update?video=clip.mp4",
                            {"asset": "assets/memes/b.gif", "mode": "cutaway"})
        assert status == 200 and data["event"]["mode"] == "cutaway"
        status, data = post("/api/events/event_001/update?video=clip.mp4", {"factor": 1.2})
        assert status == 200 and data["event"]["factor"] == 1.2
        status, data = post("/api/events/event_001/update?video=clip.mp4", {"asset": "x"})
        assert status == 400

        status, data = post("/api/events/add?video=clip.mp4",
                            {"start": 12, "asset": "assets/memes/a.png"})
        assert status == 201 and data["event"]["id"] == "event_003"
        assert data["event"]["status"] == "accepted"
        status, data = post("/api/events/add?video=clip.mp4",
                            {"start": 12, "asset": "../secret.png"})
        assert status == 400
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_static_ui_bien_tap_tran_man_hinh_goi_y_va_zoom():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    css = (STATIC_DIR / "style.css").read_text(encoding="utf-8")
    assert 'id="add-meme-button"' in html and 'id="meme-overlay-video"' in html
    for needle in ("/api/suggestions?", "/api/events/add?", 'data-mode="cutaway"',
                   "Tràn màn hình", "event-factor", "pro:["):
        assert needle in js
    # thẻ gợi ý dùng data-pick: renderLibrary gắn onclick cho mọi [data-asset] trên trang
    assert "data-pick=" in js and 'class="suggestion-card' in js
    assert "#meme-overlay.cutaway" in css and "backdrop-filter" in css
