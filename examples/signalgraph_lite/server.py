"""Local-only demo HTTP server. No database, model calls, or runtime dependencies."""

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .engine import load_dataset, snapshot

STATIC = Path(__file__).parent / 'static'
ASSETS = {
    '/': ('index.html', 'text/html'),
    '/app.js': ('app.js', 'text/javascript'),
    '/style.css': ('style.css', 'text/css'),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in ('/api/snapshot', '/api/health'):
            try:
                result = (
                    snapshot(load_dataset())
                    if path.endswith('snapshot')
                    else {'status': 'ok', 'mode': 'offline-demo'}
                )
                self.respond(HTTPStatus.OK, json.dumps(result).encode(), 'application/json')
            except (ValueError, OSError, KeyError, TypeError):
                self.respond(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    b'{"error":"Demo data could not be loaded; inspect the fixture."}',
                    'application/json',
                )
        elif path in ASSETS:
            file, mime = ASSETS[path]
            self.respond(HTTPStatus.OK, (STATIC / file).read_bytes(), mime)
        else:
            self.respond(HTTPStatus.NOT_FOUND, b'{"error":"Not found"}', 'application/json')

    def respond(self, status: HTTPStatus, body: bytes, mime: str) -> None:
        self.send_response(status)
        self.send_header('Content-Type', f'{mime}; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header(
            'Content-Security-Policy',
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    load_dataset()  # Fail before listening if the fixture is broken.
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'SignalGraph Lite • offline demo • http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
