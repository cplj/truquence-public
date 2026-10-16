"""Local HTTP API and synthetic examples. Uploaded CSV bytes are never saved."""
import argparse
import base64
import binascii
import io
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer as BaseHTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
if __package__:
    from .core import MAX_FILE_BYTES, reconcile
else:
    from core import MAX_FILE_BYTES, reconcile

ROOT = Path(__file__).resolve().parent
HOST, PORT = "127.0.0.1", 8769
ORIGIN = f"http://{HOST}:{PORT}"
MAX_BODY_BYTES = (MAX_FILE_BYTES * 8) // 3 + 4096
SAMPLES = {"dirty": "billed_dirty.csv", "clean": "billed_clean.csv", "unknown": "billed_aggregate.csv"}


class HTTPServer(ThreadingMixIn, BaseHTTPServer):
    """Keep local clients independent without creating unbounded worker threads."""
    daemon_threads = True
    max_connections = 8
    header_timeout = 5
    body_timeout = 5

    def __init__(self, *args, **kwargs):
        self._slots = threading.BoundedSemaphore(self.max_connections)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            try:
                request.settimeout(0.1)
                body = b'{"error":"SERVER_BUSY","state":"Unknown"}'
                request.sendall(b"HTTP/1.0 503 Service Unavailable\r\n"
                                b"Content-Type: application/json\r\n"
                                b"Connection: close\r\nContent-Length: "
                                + str(len(body)).encode() + b"\r\n\r\n" + body)
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class DeadlineReader(io.RawIOBase):
    """Apply one total deadline across all socket reads, including drip feeds."""
    def __init__(self, connection, timeout):
        super().__init__()
        self.connection = connection
        self.set_deadline(timeout)

    def set_deadline(self, timeout):
        self.deadline = time.monotonic() + timeout

    def readable(self):
        return True

    def readinto(self, buffer):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("request deadline exceeded")
        self.connection.settimeout(remaining)
        return self.connection.recv_into(buffer)


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.rfile.close()
        self._reader = DeadlineReader(self.connection, getattr(self.server, "header_timeout", 5))
        self.rfile = io.BufferedReader(self._reader)

    def log_message(self, *args):
        pass

    def respond(self, status, data, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def error(self, status, code):
        self.respond(status, json.dumps({"error": code, "state": "Unknown"}).encode())

    def host_allowed(self):
        return self.headers.get_all("Host") == [f"{HOST}:{self.server.server_port}"]

    def do_GET(self):
        if not self.host_allowed():
            return self.error(403, "HOST_REJECTED")
        assets = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                  "/style.css": ("style.css", "text/css; charset=utf-8")}
        if self.path in assets:
            name, kind = assets[self.path]
            return self.respond(200, (ROOT / "web" / name).read_bytes(), kind)
        if self.path.startswith("/sample/") and self.path[8:] in SAMPLES:
            name = self.path[8:]
            payload = {"usage_csv_base64": base64.b64encode((ROOT / "samples/usage.csv").read_bytes()).decode(),
                       "billed_csv_base64": base64.b64encode((ROOT / "samples" / SAMPLES[name]).read_bytes()).decode(),
                       "usage_name": "usage.csv", "billed_name": SAMPLES[name],
                       "confirm_atomic_events": name != "unknown"}
            return self.respond(200, json.dumps(payload).encode())
        return self.error(404, "NOT_FOUND")

    def do_POST(self):
        origins = self.headers.get_all("Origin")
        if not self.host_allowed() or origins not in (None, [f"http://{HOST}:{self.server.server_port}"]):
            return self.error(403, "ORIGIN_OR_HOST_REJECTED")
        if self.path != "/check":
            return self.error(404, "NOT_FOUND")
        if self.headers.get("Transfer-Encoding") is not None:
            return self.error(400, "TRANSFER_ENCODING_UNSUPPORTED")
        lengths = self.headers.get_all("Content-Length") or []
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0]) > 8:
            return self.error(411, "CONTENT_LENGTH_REQUIRED")
        length = int(lengths[0])
        if not 0 < length <= MAX_BODY_BYTES:
            return self.error(413, "BODY_TOO_LARGE_OR_EMPTY")
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
            return self.error(415, "JSON_REQUIRED")
        try:
            self._reader.set_deadline(getattr(self.server, "body_timeout", 5))
            body = self.rfile.read(length)
            if len(body) != length:
                return self.error(400, "INCOMPLETE_BODY")
            request = json.loads(body, object_pairs_hook=unique_object)
            if (type(request) is not dict or set(request) != {"usage_csv_base64", "billed_csv_base64", "confirm_atomic_events"}
                    or type(request["confirm_atomic_events"]) is not bool):
                return self.error(400, "INVALID_REQUEST")
            for key in ["usage_csv_base64", "billed_csv_base64"]:
                if type(request[key]) is not str:
                    return self.error(400, "INVALID_REQUEST")
            usage = base64.b64decode(request["usage_csv_base64"], validate=True)
            billed = base64.b64decode(request["billed_csv_base64"], validate=True)
            result = reconcile(usage, billed, request["confirm_atomic_events"])
            response = json.dumps(result, ensure_ascii=True).encode()
        except MemoryError:
            return self.respond(503, b'{"error":"INPUT_RESOURCE_LIMIT","state":"Unknown"}')
        except TimeoutError:
            return self.error(408, "REQUEST_TIMEOUT")
        except (ValueError, binascii.Error, RecursionError):
            return self.error(400, "INVALID_JSON_OR_BASE64")
        self.respond(200, response)


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        server = HTTPServer((HOST, PORT), Handler)
    except OSError as error:
        print(json.dumps({"error": type(error).__name__, "state": "Unknown"}), flush=True)
        return 2
    print(f"Local API and synthetic examples at {ORIGIN}; no uploaded files are stored.", flush=True)
    with server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
