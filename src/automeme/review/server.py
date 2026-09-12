"""HTTP server loopback cho giao diện review, không phụ thuộc web framework."""
from __future__ import annotations

import json
import mimetypes
import re
import secrets
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from pydantic import ValidationError

from ..timeline.schema import TimelineError
from ..utils.logger import log
from .service import EventPatch, ReviewError, ReviewSession

STATIC_DIR = Path(__file__).with_name("static")
MAX_JSON_BYTES = 64 * 1024
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ReviewHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], session: ReviewSession):
        if address[0].casefold() not in LOOPBACK_HOSTS:
            raise ValueError("Giao diện review chỉ được bind vào loopback.")
        self.review_session = session
        self.session_token = secrets.token_urlsafe(24)
        super().__init__(address, ReviewHandler)


class ReviewHandler(BaseHTTPRequestHandler):
    server: ReviewHTTPServer

    def do_GET(self) -> None:  # noqa: N802 - tên do BaseHTTPRequestHandler quy định
        parsed = urlparse(self.path)
        if parsed.path == "/":
            html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
            html = html.replace("__AUTOMEME_TOKEN__", self.server.session_token)
            self._bytes(
                HTTPStatus.OK,
                html.encode("utf-8"),
                "text/html; charset=utf-8",
                cookie=True,
            )
            return
        if parsed.path in {"/app.js", "/style.css"}:
            filename = parsed.path.removeprefix("/")
            content_type = "text/javascript" if filename.endswith(".js") else "text/css"
            self._bytes(
                HTTPStatus.OK,
                (STATIC_DIR / filename).read_bytes(),
                f"{content_type}; charset=utf-8",
            )
            return
        if not self._authorized():
            self._json(HTTPStatus.FORBIDDEN, {"error": "Phiên review không hợp lệ."})
            return
        try:
            if parsed.path == "/api/state":
                state = self.server.review_session.state()
                for event in state["events"]:
                    event["preview_url"] = "/media/asset?id=" + quote(event["id"], safe="")
                state["video_url"] = "/media/video"
                self._json(HTTPStatus.OK, state)
                return
            if parsed.path == "/media/video":
                self._serve_file(self.server.review_session.video)
                return
            if parsed.path == "/media/asset":
                event_id = (parse_qs(parsed.query).get("id") or [""])[0]
                self._serve_file(self.server.review_session.event_asset(event_id))
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "Không có endpoint này."})
        except (ReviewError, TimelineError, FileNotFoundError, OSError) as exc:
            self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802 - tên do BaseHTTPRequestHandler quy định
        if not self._authorized(require_header=True):
            self._json(HTTPStatus.FORBIDDEN, {"error": "Phiên review không hợp lệ."})
            return
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/render":
                output = self.server.review_session.render()
                self._json(HTTPStatus.OK, {"ok": True, "output": str(output)})
                return
            match = re.fullmatch(r"/api/events/([^/]+)/(accept|reject|update)", parsed.path)
            if match is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Không có endpoint này."})
                return
            event_id, action = unquote(match.group(1)), match.group(2)
            if action == "update":
                patch = EventPatch.model_validate(self._read_json())
                timeline = self.server.review_session.update(event_id, patch)
            else:
                status = "accepted" if action == "accept" else "rejected"
                timeline = self.server.review_session.set_status(event_id, status)
            self._json(HTTPStatus.OK, {
                "ok": True,
                "event": next(
                    event.model_dump(mode="json")
                    for event in timeline.events if event.id == event_id
                ),
            })
        except (ReviewError, TimelineError, ValidationError, ValueError, OSError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception:
            log.exception("Lỗi không mong đợi trong review server")
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Lỗi nội bộ khi review."})

    def log_message(self, format: str, *args: Any) -> None:
        log.debug("Review HTTP: " + format, *args)

    def _authorized(self, *, require_header: bool = False) -> bool:
        token = self.server.session_token
        header_ok = secrets.compare_digest(self.headers.get("X-Automeme-Token", ""), token)
        if require_header:
            return header_ok
        cookie = self.headers.get("Cookie", "")
        cookie_ok = any(
            part.strip() == f"automeme_session={token}" for part in cookie.split(";")
        )
        return header_ok or cookie_ok

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ReviewError("Content-Length không hợp lệ.") from exc
        if length <= 0 or length > MAX_JSON_BYTES:
            raise ReviewError("JSON rỗng hoặc vượt giới hạn 64 KB.")
        try:
            payload = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReviewError("Body không phải JSON hợp lệ.") from exc
        if not isinstance(payload, dict):
            raise ReviewError("Body JSON phải là object.")
        return payload

    def _serve_file(self, path: Path) -> None:
        path = Path(path)
        size = path.stat().st_size
        start, end = 0, max(0, size - 1)
        status = HTTPStatus.OK
        range_header = self.headers.get("Range")
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if match is None or not any(match.groups()):
                self._range_error(size)
                return
            first, last = match.groups()
            if first:
                start = int(first)
                end = int(last) if last else end
            else:
                suffix = int(last)
                start = max(0, size - suffix)
            end = min(end, size - 1)
            if start < 0 or start > end or start >= size:
                self._range_error(size)
                return
            status = HTTPStatus.PARTIAL_CONTENT

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        length = max(0, end - start + 1)
        try:
            self.send_response(status)
            self._security_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with open(path, "rb") as file:
                file.seek(start)
                remaining = length
                while remaining:
                    chunk = file.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # Trình duyệt thường hủy request Range cũ ngay khi người dùng tua/đóng tab.
            log.debug("Client đã hủy request media: %s", path.name)

    def _range_error(self, size: int) -> None:
        try:
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self._security_headers()
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        self._bytes(
            status,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _bytes(self, status: HTTPStatus, data: bytes, content_type: str,
               *, cookie: bool = False) -> None:
        try:
            self.send_response(status)
            self._security_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            if cookie:
                self.send_header(
                    "Set-Cookie",
                    f"automeme_session={self.server.session_token}; HttpOnly; "
                    "SameSite=Strict; Path=/",
                )
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            log.debug("Client đã đóng kết nối trước khi nhận xong response.")

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "media-src 'self'; connect-src 'self'; frame-ancestors 'none'",
        )


def create_review_server(session: ReviewSession, *, port: int = 8765) -> ReviewHTTPServer:
    if not 0 <= port <= 65535:
        raise ValueError("Port phải nằm trong khoảng 0–65535.")
    return ReviewHTTPServer(("127.0.0.1", port), session)


def serve_review(session: ReviewSession, *, port: int = 8765,
                 open_browser: bool = True) -> None:
    server = create_review_server(session, port=port)
    actual_port = server.server_address[1]
    url = f"http://127.0.0.1:{actual_port}/"
    log.info("Review UI: %s — nhấn Ctrl+C để dừng.", url)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        log.info("Đã dừng Review UI.")
    finally:
        server.server_close()
