import http.client
import json
import threading

import pytest

from automeme.config import load_settings
from automeme.review.server import STATIC_DIR, create_review_server
from automeme.review.service import (
    EventPatch,
    ReviewError,
    ReviewSession,
    apply_event_patch,
)
from automeme.timeline.schema import MemeEvent, Timeline, load_timeline, save_timeline
from automeme.utils.files import write_json
from automeme.workspace import paths_for


@pytest.fixture
def review_project(tmp_path):
    settings = load_settings(env={}, root=tmp_path)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"0123456789")
    assets = tmp_path / "assets" / "memes"
    assets.mkdir(parents=True)
    (assets / "a.png").write_bytes(b"PNG-A")
    (assets / "b.gif").write_bytes(b"GIF-B")
    timeline_path = tmp_path / "data" / "timelines" / "clip.timeline.json"
    save_timeline(timeline_path, Timeline(video=video.name, events=[
        MemeEvent(
            id="event_001",
            start=1,
            duration=1,
            asset="assets/memes/a.png",
            reason="bất ngờ",
            query="surprised reaction",
        ),
    ]))
    transcript = paths_for(video, settings).transcript
    write_json(transcript, {
        "segments": [{"id": 0, "start": 0.5, "end": 1.5, "text": "Xin chào."}],
    })
    output = tmp_path / "data" / "output" / "clip_automeme.mp4"
    session = ReviewSession(
        video=video,
        timeline_path=timeline_path,
        settings=settings,
        output=output,
        video_duration=10,
        render_callback=lambda: output,
    )
    return session


def test_apply_event_patch_khong_sua_timeline_goc():
    timeline = Timeline(video="a.mp4", events=[
        MemeEvent(id="e1", start=1, duration=1, asset="a.png"),
    ])
    result = apply_event_patch(
        timeline,
        "e1",
        EventPatch(start=2.5, duration=1.2, position="center", scale=0.4),
    )
    assert timeline.events[0].start == 1
    assert result.events[0].start == 2.5
    assert result.events[0].position == "center" and result.events[0].scale == 0.4


def test_apply_event_patch_bao_event_khong_ton_tai():
    with pytest.raises(ReviewError, match="Không có sự kiện"):
        apply_event_patch(Timeline(video="a.mp4"), "missing", EventPatch(start=1))


def test_review_session_state_va_cac_thao_tac(review_project):
    session = review_project
    state = session.state()
    assert state["active_count"] == 1
    assert state["assets"] == ["assets/memes/a.png", "assets/memes/b.gif"]
    assert state["transcript"][0]["text"] == "Xin chào."

    session.set_status("event_001", "accepted")
    session.update("event_001", EventPatch(
        start=2,
        duration=1.5,
        asset="assets/memes/b.gif",
        position="top-left",
        scale=0.25,
    ))
    event = load_timeline(session.timeline_path).events[0]
    assert event.status == "accepted" and event.asset.endswith("b.gif")
    assert event.start == 2 and event.position == "top-left"

    session.set_status("event_001", "rejected")
    assert session.state()["active_count"] == 0


def test_review_session_chan_asset_ngoai_thu_vien_va_timing_sai(review_project):
    with pytest.raises(ReviewError, match="Asset thay thế"):
        review_project.update("event_001", EventPatch(asset="C:/secret.txt"))
    with pytest.raises(ReviewError, match="video chỉ dài"):
        review_project.update("event_001", EventPatch(start=9.5, duration=2))
    assert load_timeline(review_project.timeline_path).events[0].start == 1


def test_review_session_goi_render_callback(review_project):
    assert review_project.render() == review_project.output


def test_static_ui_co_du_thanh_phan_chinh():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert "<video" in html and "Accept" in html and "Reject" in html
    assert "/api/render" in js and "updateOverlay" in js


def test_review_server_auth_api_range_va_cap_nhat(review_project):
    server = create_review_server(review_project, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    try:
        connection.request("GET", "/")
        response = connection.getresponse()
        assert response.status == 200
        assert "__AUTOMEME_TOKEN__" not in response.read().decode("utf-8")
        cookie = response.getheader("Set-Cookie").split(";", 1)[0]

        connection.request("GET", "/api/state")
        forbidden = connection.getresponse()
        assert forbidden.status == 403
        forbidden.read()

        connection.request("GET", "/api/state", headers={"Cookie": cookie})
        state_response = connection.getresponse()
        state = json.loads(state_response.read())
        assert state_response.status == 200 and state["events"][0]["preview_url"]

        connection.request("GET", "/media/video", headers={
            "Cookie": cookie,
            "Range": "bytes=2-5",
        })
        media = connection.getresponse()
        assert media.status == 206 and media.read() == b"2345"
        assert media.getheader("Content-Range") == "bytes 2-5/10"

        connection.request("POST", "/api/events/event_001/accept")
        forbidden = connection.getresponse()
        assert forbidden.status == 403
        forbidden.read()

        connection.request(
            "POST",
            "/api/events/event_001/accept",
            headers={"X-Automeme-Token": server.session_token},
        )
        accepted = connection.getresponse()
        assert accepted.status == 200
        assert json.loads(accepted.read())["event"]["status"] == "accepted"

        body = json.dumps({"start": 3.0}).encode()
        connection.request(
            "POST",
            "/api/events/event_001/update",
            body=body,
            headers={
                "X-Automeme-Token": server.session_token,
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        updated = connection.getresponse()
        assert updated.status == 200
        assert json.loads(updated.read())["event"]["start"] == 3.0

        connection.request(
            "POST",
            "/api/render",
            headers={"X-Automeme-Token": server.session_token},
        )
        rendered = connection.getresponse()
        assert rendered.status == 200
        assert json.loads(rendered.read())["output"].endswith("clip_automeme.mp4")
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_review_server_tu_choi_bind_ra_mang(review_project):
    with pytest.raises(ValueError, match="loopback"):
        from automeme.review.server import ReviewHTTPServer

        ReviewHTTPServer(("0.0.0.0", 0), review_project)
