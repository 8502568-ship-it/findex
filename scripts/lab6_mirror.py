from __future__ import annotations

import argparse
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    pages = 220

    def do_GET(self) -> None:  # noqa: N802
        time.sleep(0.05)
        if self.path == "/robots.txt":
            body = b"User-agent: *\nAllow: /\n"
        elif self.path.startswith("/page/"):
            try:
                n = int(self.path.split("/", 2)[2].split("?", 1)[0])
            except ValueError:
                self.send_error(404)
                return
            if not 0 <= n < self.pages:
                self.send_error(404)
                return
            body = (
                f"<html><head><title>Local page {n}</title></head><body>"
                f"Async crawler benchmark page {n}. "
                f"<a href='/page/{(n + 1) % self.pages}'>next</a> "
                f"<a href='/page/{(n + 7) % self.pages}?b=2&a=1#frag'>other</a>"
                "</body></html>"
            ).encode()
        else:
            body = b"<a href='/page/0'>start</a>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"http://127.0.0.1:{args.port}/page/0", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
