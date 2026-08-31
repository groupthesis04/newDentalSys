from __future__ import annotations

import argparse
import hmac
import json
import mimetypes
import os
import secrets
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.mysql_store import MySQLStore

from backend import core
from backend.routes.auth import AuthRoutes
from backend.routes.patients import PatientRoutes
from backend.routes.appointments import AppointmentRoutes
from backend.routes.availability import AvailabilityRoutes
from backend.routes.treatments import TreatmentRoutes
from backend.routes.services import ServiceRoutes
from backend.routes.messages import MessageRoutes
from backend.routes.notifications import NotificationRoutes
from backend.core import (
    BASE_DIR,
    COOKIE_SECURE,
    DATA_LOCK,
    MAX_REQUEST_BYTES,
    PUBLIC_DIR,
    RATE_LIMITER,
    REMEMBER_SESSION_TTL_SECONDS,
    SESSION_COOKIE,
    SESSION_LOCK,
    SESSION_STORE,
    SESSION_TTL_SECONDS,
    find_user_by_id,
    load_data,
    make_id,
    public_user,
    reject_duplicate_json_keys,
    sanitize_payload,
    utc_now,
)


class DentalRequestHandler(
    AuthRoutes,
    PatientRoutes,
    AppointmentRoutes,
    AvailabilityRoutes,
    TreatmentRoutes,
    ServiceRoutes,
    MessageRoutes,
    NotificationRoutes,
    BaseHTTPRequestHandler,
):
    server_version = "DentalRecordSystem/2.0"
    sys_version = ""

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
            "script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
            "font-src 'self'; connect-src 'self'; object-src 'none'",
        )
        if COOKIE_SECURE:
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:
        return

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, POST, PATCH, DELETE, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            if not self.prepare_api_request(parsed.path):
                return
            self.handle_api_get(parsed.path)
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Route not found."})
            return
        if not self.prepare_api_request(parsed.path):
            return
        self.handle_api_post(parsed.path)

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        if not self.prepare_api_request(parsed.path):
            return
        if parsed.path == "/api/profile":
            self.update_profile()
            return
        if parsed.path == "/api/appointments":
            self.update_appointment()
            return
        if parsed.path == "/api/availability":
            self.update_availability()
            return
        if parsed.path == "/api/patients":
            self.update_patient()
            return
        if parsed.path == "/api/records":
            self.update_record()
            return
        if parsed.path == "/api/feedback":
            self.update_feedback()
            return
        if parsed.path == "/api/notifications":
            self.mark_notifications_read()
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Route not found."})

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if not self.prepare_api_request(parsed.path):
            return
        if parsed.path == "/api/services":
            self.delete_service()
            return
        if parsed.path == "/api/promos":
            self.delete_promo()
            return
        if parsed.path == "/api/feedback":
            self.delete_feedback()
            return
        if parsed.path == "/api/patients":
            self.delete_patient()
            return
        if parsed.path == "/api/records":
            self.delete_record()
            return
        if parsed.path == "/api/availability":
            self.delete_availability()
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Route not found."})

    def client_ip(self) -> str:
        return str(self.client_address[0] if self.client_address else "unknown")

    def prepare_api_request(self, path: str) -> bool:
        method = self.command.upper()
        if method == "GET":
            limit, window = (180, 60)
        elif path == "/api/login":
            limit, window = (5, 300)
        elif path == "/api/register":
            limit, window = (4, 3600)
        elif path == "/api/feedback" and method == "POST":
            limit, window = (5, 600)
        elif path == "/api/appointments" and method == "POST":
            limit, window = (10, 600)
        elif path == "/api/messages" and method == "POST":
            limit, window = (30, 60)
        else:
            limit, window = (60, 60)

        retry_after = RATE_LIMITER.check(
            f"{self.client_ip()}:{method}:{path}", limit, window
        )
        if retry_after:
            self.send_json(
                HTTPStatus.TOO_MANY_REQUESTS,
                {"error": "Too many requests. Please wait before trying again."},
                {"Retry-After": str(retry_after)},
            )
            return False

        if method in {"POST", "PATCH", "DELETE"} and not self.is_same_origin_request():
            self.send_error_json(HTTPStatus.FORBIDDEN, "Cross-site requests are not allowed.")
            return False
        return True

    def is_same_origin_request(self) -> bool:
        fetch_site = self.headers.get("Sec-Fetch-Site", "").strip().lower()
        if fetch_site == "cross-site":
            return False
        origin = self.headers.get("Origin", "").strip()
        if not origin:
            return True
        parsed = urlparse(origin)
        host = self.headers.get("Host", "").strip().lower()
        return parsed.scheme in {"http", "https"} and parsed.netloc.lower() == host

    def serve_static(self, raw_path: str) -> None:
        requested = unquote(raw_path.lstrip("/"))
        if not requested:
            requested = "index.html"
        static_path = (PUBLIC_DIR / requested).resolve()
        public_root = PUBLIC_DIR.resolve()

        if static_path != public_root and public_root not in static_path.parents:
            self.send_error(HTTPStatus.FORBIDDEN)
            return

        if static_path.is_dir():
            static_path = static_path / "index.html"

        if not static_path.exists() or not static_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(static_path.name)[0] or "application/octet-stream"
        body = static_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if static_path.suffix in {".html", ".css", ".js"}:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Invalid Content-Length header.") from error
        if length < 0:
            raise ValueError("Invalid Content-Length header.")
        if length > MAX_REQUEST_BYTES:
            raise ValueError("Request body is too large.")
        if length == 0:
            return {}
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise ValueError("Content-Type must be application/json.")
        try:
            raw_body = self.rfile.read(length).decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ValueError("Request body must use UTF-8.") from error
        payload = json.loads(raw_body, object_pairs_hook=reject_duplicate_json_keys)
        sanitized = sanitize_payload(payload)
        if str(sanitized.pop("_website", "")).strip():
            raise ValueError("Unable to process this request.")
        return sanitized

    def send_json(
        self,
        status: int | HTTPStatus,
        payload: dict | list,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: int | HTTPStatus, message: str) -> None:
        self.send_json(status, {"error": message})

    def cookie_token(self) -> str | None:
        cookie_header = self.headers.get("Cookie", "")
        for part in cookie_header.split(";"):
            name, _, value = part.strip().partition("=")
            if name == SESSION_COOKIE and value:
                return value
        return None

    def current_session(self) -> tuple[str, dict[str, object]] | None:
        token = self.cookie_token()
        if not token:
            return None
        now = time.time()
        with SESSION_LOCK:
            session = SESSION_STORE.get(token)
            if not session:
                return None
            if float(session.get("expires_at", 0)) <= now:
                SESSION_STORE.pop(token, None)
                return None
            return token, session

    def create_session(self, user_id: str, remember: bool = False) -> tuple[str, str, int]:
        token = make_id("session")
        csrf_token = secrets.token_urlsafe(32)
        max_age = REMEMBER_SESSION_TTL_SECONDS if remember else SESSION_TTL_SECONDS
        with SESSION_LOCK:
            SESSION_STORE[token] = {
                "user_id": user_id,
                "csrf_token": csrf_token,
                "created_at": utc_now(),
                "expires_at": time.time() + max_age,
            }
        return token, csrf_token, max_age

    def session_cookie(self, token: str, max_age: int) -> str:
        cookie = (
            f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"
        )
        return f"{cookie}; Secure" if COOKIE_SECURE else cookie

    def valid_csrf_token(self, session: dict[str, object]) -> bool:
        provided = self.headers.get("X-CSRF-Token", "")
        expected = str(session.get("csrf_token", ""))
        return bool(provided and expected and hmac.compare_digest(provided, expected))

    def current_user(self, data: dict) -> dict | None:
        active = self.current_session()
        if not active:
            return None
        _, session = active
        return find_user_by_id(data, str(session["user_id"]))

    def require_user(self, data: dict) -> dict | None:
        active = self.current_session()
        if active:
            _, session = active
            user = find_user_by_id(data, str(session["user_id"]))
            if user:
                if self.command in {"POST", "PATCH", "DELETE"} and not self.valid_csrf_token(session):
                    self.send_error_json(
                        HTTPStatus.FORBIDDEN,
                        "Security token expired. Refresh the page and try again.",
                    )
                    return None
                return user
        self.send_error_json(HTTPStatus.UNAUTHORIZED, "Please log in to continue.")
        return None

    def require_doctor(self, data: dict) -> dict | None:
        user = self.require_user(data)
        if not user:
            return None
        if user["role"] != "doctor":
            self.send_error_json(HTTPStatus.FORBIDDEN, "Only doctor accounts can use this feature.")
            return None
        return user

    def handle_api_get(self, path: str) -> None:
        if path == "/api/session":
            with DATA_LOCK:
                data = load_data()
                user = self.current_user(data)
                active = self.current_session() if user else None
                csrf_token = str(active[1].get("csrf_token", "")) if active else ""
            self.send_json(
                HTTPStatus.OK,
                {
                    "authenticated": bool(user),
                    "user": public_user(user) if user else None,
                    "csrf_token": csrf_token,
                },
            )
            return
        if path == "/api/appointments":
            self.list_appointments()
            return
        if path == "/api/availability":
            self.list_availability()
            return
        if path == "/api/records":
            self.list_records()
            return
        if path == "/api/patients":
            self.list_patients()
            return
        if path == "/api/messages":
            self.list_messages()
            return
        if path == "/api/notifications":
            self.list_notifications()
            return
        if path == "/api/services":
            self.list_services()
            return
        if path == "/api/promos":
            self.list_promos()
            return
        if path == "/api/feedback":
            self.list_feedback()
            return
        self.send_error_json(HTTPStatus.NOT_FOUND, "Route not found.")

    def handle_api_post(self, path: str) -> None:
        try:
            payload = self.read_json()
        except (ValueError, json.JSONDecodeError) as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        if path == "/api/register":
            self.register(payload)
            return
        if path == "/api/login":
            self.login(payload)
            return
        if path == "/api/logout":
            self.logout()
            return
        if path == "/api/patients":
            self.create_patient(payload)
            return
        if path == "/api/appointments":
            self.create_appointment(payload)
            return
        if path == "/api/availability":
            self.create_availability(payload)
            return
        if path == "/api/records":
            self.create_record(payload)
            return
        if path == "/api/messages":
            self.create_message(payload)
            return
        if path == "/api/services":
            self.create_service(payload)
            return
        if path == "/api/promos":
            self.create_promo(payload)
            return
        if path == "/api/feedback":
            self.create_feedback(payload)
            return
        self.send_error_json(HTTPStatus.NOT_FOUND, "Route not found.")


def main() -> None:

    parser = argparse.ArgumentParser(description="Dental Record Management System")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--storage",
        choices=("mysql", "json"),
        default=os.environ.get("DRMS_STORAGE", "mysql"),
        help="Persistence backend. MySQL is the production default; JSON is for local migration tests.",
    )
    parser.add_argument(
        "--data-file",
        help="Optional JSON data file used only with --storage json.",
    )
    args = parser.parse_args()

    if args.storage == "mysql":
        if args.data_file:
            parser.error("--data-file can only be used with --storage json.")
        try:
            core.DATA_STORE = MySQLStore()
            core.DATA_STORE.initialize()
            with DATA_LOCK:
                load_data()
        except (RuntimeError, ValueError) as error:
            parser.error(str(error))
    else:
        core.DATA_STORE = None
        if args.data_file:
            core.DATA_FILE = Path(args.data_file)
            if not core.DATA_FILE.is_absolute():
                core.DATA_FILE = BASE_DIR / core.DATA_FILE

    mimetypes.add_type("text/javascript", ".js")
    server = ThreadingHTTPServer((args.host, args.port), DentalRequestHandler)
    print(
        f"Serving Dental Record Management System at http://{args.host}:{args.port} "
        f"using {args.storage.upper()} storage"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
