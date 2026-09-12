"""HTTP server loopback cho AutoMeme Studio, không cần web framework."""
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

from ..review.service import EventPatch, ReviewError
from ..timeline.schema import TimelineError
from ..utils.logger import log
from .service import JobRequest, MetadataPatch, StudioError, StudioService

STATIC_DIR = Path(__file__).with_name("static")
MAX_JSON_BYTES = 64 * 1024
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class StudioHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], service: StudioService):
        if address[0].casefold() not in LOOPBACK_HOSTS:
            raise ValueError("AutoMeme Studio chỉ được bind vào loopback.")
        self.studio = service
        self.session_token = secrets.token_urlsafe(24)
        super().__init__(address, StudioHandler)


class StudioHandler(BaseHTTPRequestHandler):
    server: StudioHTTPServer

    def do_GET(self) -> None:  # noqa: N802
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
        if parsed.path.startswith("/assets/"):
            self._serve_static(parsed.path.removeprefix("/assets/"))
            return
        if not self._authorized():
            self._json(HTTPStatus.FORBIDDEN, {"error": "Phiên Studio không hợp lệ."})
            return
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/dashboard":
                refresh = (query.get("refresh") or [""])[0] == "1"
                self._json(
                    HTTPStatus.OK,
                    self.server.studio.dashboard(refresh_environment=refresh),
                )
            elif parsed.path == "/api/projects":
                self._json(HTTPStatus.OK, {"projects": self.server.studio.projects()})
            elif parsed.path == "/api/job":
                self._json(HTTPStatus.OK, {"job": self.server.studio.job()})
            elif parsed.path == "/api/library":
                self._json(HTTPStatus.OK, {"items": self.server.studio.library()})
            elif parsed.path == "/api/project":
                session = self.server.studio.review(self._query(query, "video"))
                state = session.state()
                video_name = quote(session.video.name, safe="")
                for event in state["events"]:
                    event["preview_url"] = (
                        f"/media/event?video={video_name}&id={quote(event['id'], safe='')}"
                    )
                state["video_url"] = f"/media/video?video={video_name}"
                state["output_url"] = f"/media/output?video={video_name}"
                state["output_exists"] = session.output.is_file()
                self._json(HTTPStatus.OK, state)
            elif parsed.path == "/media/video":
                self._serve_file(self.server.studio.video_path(self._query(query, "video")))
            elif parsed.path == "/media/output":
                self._serve_file(self.server.studio.output_path(self._query(query, "video")))
            elif parsed.path == "/media/event":
                session = self.server.studio.review(self._query(query, "video"))
                self._serve_file(session.event_asset(self._query(query, "id")))
            elif parsed.path == "/media/library":
                self._serve_file(self.server.studio.library_asset(self._query(query, "id")))
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Không có endpoint này."})
        except (StudioError, ReviewError, TimelineError, FileNotFoundError, OSError) as exc:
            self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized(require_header=True):
            self._json(HTTPStatus.FORBIDDEN, {"error": "Phiên Studio không hợp lệ."})
            return
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/videos/upload":
                length = self._content_length()
                item = self.server.studio.upload_video(
                    self.headers.get("X-Filename", ""), self.rfile, length,
                )
                self._json(HTTPStatus.CREATED, {"ok": True, "project": item})
                return
            if parsed.path == "/api/library/upload":
                length = self._content_length()
                item = self.server.studio.upload_asset(
                    self.headers.get("X-Filename", ""), self.rfile, length,
                )
                self._json(HTTPStatus.CREATED, {
                    "ok": True,
                    "item": item.model_dump(mode="json"),
                })
                return
            if parsed.path == "/api/jobs":
                state = self.server.studio.start_job(JobRequest.model_validate(self._read_json()))
                self._json(HTTPStatus.ACCEPTED, {"ok": True, "job": state})
                return
            if parsed.path == "/api/library/popular":
                raw_limit = (query.get("limit") or ["100"])[0]
                result = self.server.studio.install_popular_library(limit=int(raw_limit))
                self._json(HTTPStatus.OK, {"ok": result["failed"] == 0, **result})
                return
            if parsed.path == "/api/library/animated":
                raw_limit = (query.get("limit") or ["30"])[0]
                result = self.server.studio.install_animated_library(limit=int(raw_limit))
                self._json(HTTPStatus.OK, {"ok": result["failed"] == 0, **result})
                return
            if parsed.path == "/api/library/sfx":
                raw_limit = (query.get("limit") or ["30"])[0]
                result = self.server.studio.install_sfx_library(limit=int(raw_limit))
                self._json(HTTPStatus.OK, {"ok": result["failed"] == 0, **result})
                return
            if parsed.path == "/api/render":
                output = self.server.studio.review(self._query(query, "video")).render()
                self._json(HTTPStatus.OK, {"ok": True, "output": str(output)})
                return
            metadata = re.fullmatch(r"/api/library/([^/]+)", parsed.path)
            if metadata:
                item_id = unquote(metadata.group(1))
                item = self.server.studio.update_metadata(
                    item_id, MetadataPatch.model_validate(self._read_json()),
                )
                self._json(HTTPStatus.OK, {
                    "ok": True,
                    "item": item.model_dump(mode="json"),
                })
                return
            event_match = re.fullmatch(
                r"/api/events/([^/]+)/(accept|reject|update)", parsed.path,
            )
            if event_match:
                event_id, action = unquote(event_match.group(1)), event_match.group(2)
                session = self.server.studio.review(self._query(query, "video"))
                if action == "update":
                    patch = EventPatch.model_validate(self._read_json())
                    timeline = session.update(event_id, patch)
                else:
                    status = "accepted" if action == "accept" else "rejected"
                    timeline = session.set_status(event_id, status)
                event = next(event for event in timeline.events if event.id == event_id)
                self._json(HTTPStatus.OK, {
                    "ok": True,
                    "event": event.model_dump(mode="json"),
                })
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "Không có endpoint này."})
        except (StudioError, ReviewError, TimelineError, ValidationError, ValueError,
                FileNotFoundError, OSError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception:
            log.exception("Lỗi không mong đợi trong Studio server")
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Lỗi nội bộ trong Studio."})

    def log_message(self, format: str, *args: Any) -> None:
        log.debug("Studio HTTP: " + format, *args)

    def _serve_static(self, relative: str) -> None:
        path = (STATIC_DIR / unquote(relative)).resolve()
        try:
            path.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self._json(HTTPStatus.NOT_FOUND, {"error": "Không có asset này."})
            return
        if not path.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "Không có asset này."})
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix == ".mjs":
            content_type = "text/javascript"
        self._bytes(HTTPStatus.OK, path.read_bytes(), content_type)

    def _authorized(self, *, require_header: bool = False) -> bool:
        token = self.server.session_token
        header_ok = secrets.compare_digest(self.headers.get("X-Automeme-Token", ""), token)
        if require_header:
            return header_ok
        cookie = self.headers.get("Cookie", "")
        cookie_ok = any(
            part.strip() == f"automeme_studio={token}" for part in cookie.split(";")
        )
        return header_ok or cookie_ok

    def _read_json(self) -> dict[str, Any]:
        length = self._content_length()
        if length > MAX_JSON_BYTES:
            raise StudioError("JSON vượt giới hạn 64 KB.")
        try:
            payload = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StudioError("Body không phải JSON hợp lệ.") from exc
        if not isinstance(payload, dict):
            raise StudioError("Body JSON phải là object.")
        return payload

    def _content_length(self) -> int:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise StudioError("Content-Length không hợp lệ.") from exc
        if length <= 0:
            raise StudioError("Request không có dữ liệu.")
        return length

    @staticmethod
    def _query(query: dict[str, list[str]], name: str) -> str:
        value = (query.get(name) or [""])[0]
        if not value:
            raise StudioError(f"Thiếu tham số {name}.")
        return value

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
        length = max(0, end - start + 1)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        try:
            self.send_response(status)
            self._security_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with open(path, "rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining:
                    chunk = handle.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            log.debug("Client đã hủy request media: %s", path.name)

    def _range_error(self, size: int) -> None:
        self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
        self._security_headers()
        self.send_header("Content-Range", f"bytes */{size}")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        self._bytes(
            status,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _bytes(
        self,
        status: HTTPStatus,
        data: bytes,
        content_type: str,
        *,
        cookie: bool = False,
    ) -> None:
        try:
            self.send_response(status)
            self._security_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            if cookie:
                self.send_header(
                    "Set-Cookie",
                    f"automeme_studio={self.server.session_token}; HttpOnly; "
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
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
            "media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'",
        )


def create_studio_server(service: StudioService, *, port: int = 8765) -> StudioHTTPServer:
    if not 0 <= port <= 65535:
        raise ValueError("Port phải nằm trong khoảng 0–65535.")
    return StudioHTTPServer(("127.0.0.1", port), service)


def serve_studio(service: StudioService, *, port: int = 8765, open_browser: bool = True) -> None:
    server = create_studio_server(service, port=port)
    actual_port = server.server_address[1]
    url = f"http://127.0.0.1:{actual_port}/"
    log.info("AutoMeme Studio: %s — nhấn Ctrl+C để dừng.", url)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        log.info("Đã dừng AutoMeme Studio.")
    finally:
        server.server_close()
