"""Local web UI: one static page plus a JSON ``POST /ask`` endpoint. Binds to localhost only."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .answer import answer

PAGE = (Path(__file__).resolve().parent / "static" / "index.html").read_bytes()
MAX_BODY_BYTES = 16 * 1024
MAX_QUESTION_CHARS = 500


class _BadRequest(Exception):
    pass


def parse_request(raw):
    """Validate an /ask body and return ``(question, accepted_suggestions)``."""
    try:
        payload = json.loads(raw or b"{}")
    except (UnicodeDecodeError, ValueError):
        raise _BadRequest("request body must be JSON")
    if not isinstance(payload, dict):
        raise _BadRequest("request body must be a JSON object")
    question = str(payload.get("q", ""))[:MAX_QUESTION_CHARS]
    accepted = payload.get("accepted_suggestions", [])
    return question, accepted if isinstance(accepted, list) else []


def make_handler(settings, llm_client=None):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, body, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, payload):
            self._send(status, json.dumps(payload).encode(), "application/json; charset=utf-8")

        def do_GET(self):
            if self.path.split("?", 1)[0] in ("/", "/index.html"):
                self._send(200, PAGE, "text/html; charset=utf-8")
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/ask":
                return self._json(404, {"error": "not found"})
            try:
                length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                return self._json(400, {"error": "invalid Content-Length"})
            if length < 0 or length > MAX_BODY_BYTES:
                return self._json(413, {"error": f"request body must be at most {MAX_BODY_BYTES} bytes"})
            try:
                question, accepted = parse_request(self.rfile.read(length))
            except _BadRequest as error:
                return self._json(400, {"error": str(error)})
            self._json(200, answer(question, accepted, settings, llm_client))

        def log_message(self, *args):
            pass  # questions may contain health information; keep them out of the console

    return Handler


def make_server(settings, host="127.0.0.1", port=8000, llm_client=None):
    return HTTPServer((host, port), make_handler(settings, llm_client))
