from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Tuple


class DummyProbeHandler(BaseHTTPRequestHandler):
    server_version = "DummyProbeServer/1.0"

    def _set_headers(self, status: int = 200, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler signature)
        if self.path == "/ip":
            self._handle_ip()
        elif self.path == "/headers":
            self._handle_headers()
        else:
            self._set_headers(404)
            self.wfile.write(b'{"error": "not found"}')

    def _handle_ip(self) -> None:
        payload = {"ip": "127.0.0.1", "service": "dummy"}
        self._set_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def _handle_headers(self) -> None:
        headers = {key: value for key, value in self.headers.items()}
        payload = {"headers": headers}
        self._set_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def log_message(self, format: str, *args: Tuple[str, ...]) -> None:  # noqa: A003
        # Silence default stdout logging to keep test output clean.
        return


def create_server(server_address: Tuple[str, int] = ("127.0.0.1", 5001)) -> HTTPServer:
    return HTTPServer(server_address, DummyProbeHandler)


def run(server_address: Tuple[str, int] = ("127.0.0.1", 5001)) -> None:
    httpd = create_server(server_address)
    try:
        print(f"Dummy probe server listening on http://{server_address[0]}:{server_address[1]}")
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down dummy probe server.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run()
