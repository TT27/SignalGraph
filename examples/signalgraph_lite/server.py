"""Loopback investigation workbench, SQLite persistence, and a keyless offline demo."""

import argparse
import json
import sqlite3
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from .briefing import briefing, statement_diff
from .engine import load_dataset, snapshot
from .store import StaleReview, WorkspaceStore
from .temporal import replay

STATIC = Path(__file__).parent / 'static'
ASSETS = {
    '/': ('index.html', 'text/html'),
    '/app.js': ('app.js', 'text/javascript'),
    '/workspace.js': ('workspace.js', 'text/javascript'),
    '/style.css': ('style.css', 'text/css'),
    '/workspace.css': ('workspace.css', 'text/css'),
}
MAX_BODY = 4 * 1024 * 1024


def text_field(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{key} must be a non-empty string')
    return value


class Handler(BaseHTTPRequestHandler):
    store: WorkspaceStore | None = None

    def local_host(self) -> bool:
        port = cast(ThreadingHTTPServer, self.server).server_port
        allowed = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if port == 80:
            allowed.update({'127.0.0.1', 'localhost'})
        if self.headers.get('Host') not in allowed:
            self.json_response({'error': 'Unrecognized local host'}, HTTPStatus.FORBIDDEN)
            return False
        return True

    def do_GET(self) -> None:
        if not self.local_host():
            return
        parsed = urlsplit(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        workspace = query.get('workspace', ['demo'])[0]
        if path in ASSETS:
            file, mime = ASSETS[path]
            self.respond(HTTPStatus.OK, (STATIC / file).read_bytes(), mime)
            return
        try:
            if path == '/api/health':
                self.json_response(
                    {'status': 'ok', 'mode': 'offline-demo', 'persistence': self.store is not None}
                )
            elif path == '/api/snapshot':
                result = self.store.view(workspace) if self.store else snapshot(load_dataset())
                claim_map = {c['id']: c for c in result['claims']}
                for event in result['events']:
                    event['diff'] = statement_diff(
                        ' '.join(claim_map[c]['quote'] for c in event['before']),
                        ' '.join(claim_map[c]['quote'] for c in event['after']),
                    )
                self.json_response(result)
            elif path == '/api/workspaces':
                self.json_response(self.require_store().list_workspaces())
            elif path == '/api/dataset':
                self.json_response(asdict(self.require_store().dataset(workspace)))
            elif path == '/api/replay':
                data = self.require_store().dataset(workspace)
                self.json_response(
                    replay(
                        data, query.get('observed_until', [''])[0], query.get('valid_at', [''])[0]
                    )
                )
            elif path == '/api/briefing':
                body = briefing(self.require_store().view(workspace)).encode()
                self.respond(HTTPStatus.OK, body, 'text/markdown')
            else:
                self.json_response({'error': 'Not found'}, HTTPStatus.NOT_FOUND)
        except KeyError as error:
            self.json_response({'error': str(error)}, HTTPStatus.NOT_FOUND)
        except (ValueError, TypeError) as error:
            status = (
                HTTPStatus.INTERNAL_SERVER_ERROR
                if path == '/api/snapshot'
                else HTTPStatus.BAD_REQUEST
            )
            self.json_response(
                {
                    'error': str(error)
                    if status == HTTPStatus.BAD_REQUEST
                    else 'Evidence could not be loaded; inspect the dataset.'
                },
                status,
            )
        except (OSError, sqlite3.Error):
            self.json_response(
                {'error': 'Local storage is unavailable'}, HTTPStatus.INTERNAL_SERVER_ERROR
            )

    def require_store(self) -> WorkspaceStore:
        if self.store is None:
            raise ValueError('Persistent workspace is not configured')
        return self.store

    def do_POST(self) -> None:
        if not self.local_host():
            return
        # JSON-only mutations and exact Origin checks prevent browser cross-site form writes.
        origin = self.headers.get('Origin')
        expected = f'http://{self.headers.get("Host")}'
        if origin and origin != expected:
            self.json_response(
                {'error': 'Cross-origin writes are not allowed'}, HTTPStatus.FORBIDDEN
            )
            return
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            self.json_response({'error': 'Use application/json'}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                self.json_response(
                    {'error': 'JSON body must be 1 byte to 4 MiB'},
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
                return
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('Request body must be an object')
            store = self.require_store()
            workspace = payload.get('workspace', 'demo')
            if not isinstance(workspace, str):
                raise ValueError('workspace must be a string')
            path = urlsplit(self.path).path
            if path == '/api/import':
                imported = store.import_dataset(text_field(payload, 'name'), payload.get('dataset'))
                self.json_response({'workspace': imported}, HTTPStatus.CREATED)
            elif path == '/api/append':
                store.append_dataset(workspace, payload.get('dataset'))
                self.json_response({'workspace': workspace})
            elif path == '/api/review':
                result = store.save_review(
                    workspace,
                    text_field(payload, 'event_id'),
                    text_field(payload, 'status'),
                    payload.get('note', ''),
                    payload.get('version', 0),
                )
                self.json_response(result)
            elif path == '/api/watch':
                watch = store.add_watch(
                    workspace,
                    text_field(payload, 'label'),
                    payload.get('entity_id'),
                    payload.get('kind', 'all'),
                )
                self.json_response({'id': watch}, HTTPStatus.CREATED)
            elif path == '/api/watch/remove':
                store.remove_watch(workspace, text_field(payload, 'id'))
                self.json_response({'ok': True})
            elif path == '/api/alert/acknowledge':
                store.acknowledge(
                    workspace, text_field(payload, 'watch_id'), text_field(payload, 'event_id')
                )
                self.json_response({'ok': True})
            else:
                self.json_response({'error': 'Not found'}, HTTPStatus.NOT_FOUND)
        except StaleReview as error:
            self.json_response({'error': str(error)}, HTTPStatus.CONFLICT)
        except KeyError as error:
            self.json_response({'error': str(error)}, HTTPStatus.NOT_FOUND)
        except (ValueError, TypeError, AttributeError) as error:
            self.json_response({'error': str(error)}, HTTPStatus.BAD_REQUEST)
        except (OSError, sqlite3.Error):
            self.json_response(
                {'error': 'Local storage is unavailable'}, HTTPStatus.INTERNAL_SERVER_ERROR
            )

    def json_response(self, result: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.respond(status, json.dumps(result).encode(), 'application/json')

    def respond(self, status: HTTPStatus, body: bytes, mime: str) -> None:
        self.send_response(status)
        self.send_header('Content-Type', f'{mime}; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header(
            'Content-Security-Policy',
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)


def handler_for(store: WorkspaceStore) -> type[Handler]:
    class PersistentHandler(Handler):
        pass

    PersistentHandler.store = store
    return PersistentHandler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--db', type=Path, default=Path('work/signalgraph/workspace.sqlite3'))
    args = parser.parse_args()
    store = WorkspaceStore(args.db)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(store))
    print(f'SignalGraph Desk • local evidence workbench • http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
