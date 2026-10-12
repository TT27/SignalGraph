"""HTTP smoke and failure-state checks against an ephemeral loopback server."""

import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from examples.signalgraph_lite.server import Handler


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_snapshot_and_health(self) -> None:
        with urlopen(self.url + '/api/snapshot', timeout=3) as response:
            data = json.load(response)
        self.assertEqual(data['counts']['conflict'], 2)
        self.assertEqual(len(data['documents']), 12)
        with urlopen(self.url + '/api/health', timeout=3) as response:
            self.assertEqual(json.load(response)['mode'], 'offline-demo')

    def test_assets_and_security_headers(self) -> None:
        for path in ('/', '/app.js', '/style.css'):
            with urlopen(self.url + path, timeout=3) as response:
                self.assertEqual(response.status, 200)
                self.assertGreater(len(response.read()), 100)
                self.assertIn("default-src 'self'", response.headers['Content-Security-Policy'])

    def test_unknown_and_traversal_paths_are_not_served(self) -> None:
        for path in ('/unknown', '/../pyproject.toml', '/%2e%2e/pyproject.toml'):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.url + path, timeout=3)
            self.assertEqual(error.exception.code, 404)

    def test_broken_fixture_returns_explicit_error(self) -> None:
        with patch(
            'examples.signalgraph_lite.server.load_dataset', side_effect=ValueError('bad data')
        ):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.url + '/api/snapshot', timeout=3)
            self.assertEqual(error.exception.code, 500)
            self.assertIn('could not be loaded', json.load(error.exception)['error'])
