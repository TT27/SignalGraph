"""HTTP import/review/replay contracts and invalid mutation handling."""

import json
import tempfile
import threading
import unittest
from dataclasses import asdict
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from examples.signalgraph_lite.engine import load_dataset
from examples.signalgraph_lite.server import handler_for
from examples.signalgraph_lite.store import WorkspaceStore


class WorkspaceAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = WorkspaceStore(Path(self.temp.name) / 'workspace.sqlite3')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.store))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def post(self, path: str, payload: dict, headers: dict | None = None) -> dict:
        request = Request(
            self.url + path,
            json.dumps(payload).encode(),
            {'Content-Type': 'application/json', **(headers or {})},
        )
        with urlopen(request, timeout=3) as response:
            return json.load(response)

    def test_import_snapshot_and_briefing(self) -> None:
        imported = self.post('/api/import', {'name': 'Test', 'dataset': asdict(load_dataset())})
        with urlopen(self.url + '/api/snapshot?workspace=' + imported['workspace']) as response:
            result = json.load(response)
        self.assertEqual(result['workspace']['name'], 'Test')
        self.assertTrue(result['events'][0]['diff'])
        with urlopen(self.url + '/api/briefing?workspace=' + imported['workspace']) as response:
            self.assertIn('SignalGraph briefing', response.read().decode())

    def test_stale_review_returns_409(self) -> None:
        event = self.store.view('demo')['events'][0]['id']
        body = {'event_id': event, 'status': 'investigating', 'note': 'First', 'version': 0}
        self.post('/api/review', body)
        with self.assertRaises(HTTPError) as error:
            self.post('/api/review', body)
        self.assertEqual(error.exception.code, 409)

    def test_cross_origin_and_non_json_writes_are_rejected(self) -> None:
        with self.assertRaises(HTTPError) as error:
            self.post('/api/watch', {}, {'Origin': 'https://unrelated.example'})
        self.assertEqual(error.exception.code, 403)
        with self.assertRaises(HTTPError) as error:
            self.post('/api/watch', {}, {'Content-Type': 'text/plain'})
        self.assertEqual(error.exception.code, 415)

    def test_non_local_host_cannot_read_or_mutate_evidence(self) -> None:
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.url + '/api/snapshot', headers={'Host': 'unrelated.example'}))
        self.assertEqual(error.exception.code, 403)
        with self.assertRaises(HTTPError) as error:
            self.post(
                '/api/watch',
                {},
                {'Host': 'unrelated.example', 'Origin': 'http://unrelated.example'},
            )
        self.assertEqual(error.exception.code, 403)

    def test_replay_rejects_invalid_dates(self) -> None:
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + '/api/replay?observed_until=bad&valid_at=bad')
        self.assertEqual(error.exception.code, 400)

    def test_workspace_lookup_is_explicit_and_isolated(self) -> None:
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + '/api/snapshot?workspace=does-not-exist')
        self.assertEqual(error.exception.code, 404)

    def test_import_validation_returns_400_and_no_partial_workspace(self) -> None:
        with self.assertRaises(HTTPError) as error:
            self.post('/api/import', {'name': 'Bad', 'dataset': {'entities': 'bad'}})
        self.assertEqual(error.exception.code, 400)
        self.assertEqual(len(self.store.list_workspaces()), 1)
