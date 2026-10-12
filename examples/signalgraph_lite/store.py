"""Local SQLite investigations, append-only review history, and deduplicated watch alerts."""

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .engine import dataset_from_dict, load_dataset, snapshot
from .models import Dataset


class StaleReview(ValueError):
    """An analyst edited a review based on an older version."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dataset_json(data: Dataset) -> str:
    return json.dumps(asdict(data), sort_keys=True)


class WorkspaceStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    workspace TEXT NOT NULL, event_id TEXT NOT NULL, status TEXT NOT NULL,
                    note TEXT NOT NULL, version INTEGER NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(workspace, event_id)
                );
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY, workspace TEXT NOT NULL, event_id TEXT NOT NULL,
                    status TEXT NOT NULL, note TEXT NOT NULL, version INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS watches (
                    id TEXT PRIMARY KEY, workspace TEXT NOT NULL, label TEXT NOT NULL,
                    entity_id TEXT, kind TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS alerts (
                    workspace TEXT NOT NULL, watch_id TEXT NOT NULL, event_id TEXT NOT NULL,
                    seen INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
                    PRIMARY KEY(workspace, watch_id, event_id)
                );
            """)
            if not db.execute('SELECT 1 FROM workspaces WHERE id=?', ('demo',)).fetchone():
                db.execute(
                    'INSERT INTO workspaces VALUES (?,?,?,?)',
                    ('demo', 'Company signals · demo', dataset_json(load_dataset()), now()),
                )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def list_workspaces(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    'SELECT id,name,created_at FROM workspaces ORDER BY created_at,id'
                )
            ]

    def dataset(self, workspace: str) -> Dataset:
        with self.connect() as db:
            row = db.execute('SELECT payload FROM workspaces WHERE id=?', (workspace,)).fetchone()
        if row is None:
            raise KeyError('Investigation not found')
        return dataset_from_dict(json.loads(row['payload']))

    def import_dataset(self, name: str, payload: Any) -> str:
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            raise ValueError('Investigation name must have 1–100 characters')
        data = dataset_from_dict(payload)
        if not data.documents or not data.entities:
            raise ValueError('Import requires at least one document and one entity')
        workspace = uuid4().hex
        with self.connect() as db:
            db.execute(
                'INSERT INTO workspaces VALUES (?,?,?,?)',
                (workspace, name.strip(), dataset_json(data), now()),
            )
        return workspace

    def append_dataset(self, workspace: str, payload: Any) -> None:
        """Atomically append immutable records. Identical re-imports are idempotent."""
        incoming = dataset_from_dict(payload)
        if workspace == 'demo':
            raise ValueError('Demo evidence is fixed; import a new investigation before appending')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload FROM workspaces WHERE id=?', (workspace,)).fetchone()
            if row is None:
                raise KeyError('Investigation not found')
            existing = dataset_from_dict(json.loads(row['payload']))
            if incoming.periods != existing.periods:
                raise ValueError('Append must use the same comparison periods')
            merged = {}
            for name in ('entities', 'documents', 'claims'):
                records = {r.id: r for r in getattr(existing, name)}
                for record in getattr(incoming, name):
                    if record.id in records and records[record.id] != record:
                        raise ValueError(f'Immutable record {record.id} differs; use a new ID')
                    records[record.id] = record
                merged[name] = [asdict(r) for r in records.values()]
            merged['periods'] = list(existing.periods)
            updated = dataset_from_dict(json.loads(json.dumps(merged)))
            db.execute(
                'UPDATE workspaces SET payload=? WHERE id=?', (dataset_json(updated), workspace)
            )

    def view(self, workspace: str) -> dict[str, Any]:
        data = self.dataset(workspace)
        result = snapshot(data)
        with self.connect() as db:
            info = db.execute('SELECT id,name FROM workspaces WHERE id=?', (workspace,)).fetchone()
            reviews = {
                r['event_id']: dict(r)
                for r in db.execute('SELECT * FROM reviews WHERE workspace=?', (workspace,))
            }
            history = [
                dict(r)
                for r in db.execute(
                    'SELECT * FROM history WHERE workspace=? ORDER BY id DESC', (workspace,)
                )
            ]
            watches = [
                dict(r)
                for r in db.execute(
                    'SELECT * FROM watches WHERE workspace=? ORDER BY label,id', (workspace,)
                )
            ]
            for watch in watches:
                for event in result['events']:
                    if (
                        watch['entity_id'] is None or watch['entity_id'] == event['entity_id']
                    ) and (watch['kind'] == 'all' or watch['kind'] == event['kind']):
                        db.execute(
                            'INSERT OR IGNORE INTO alerts VALUES (?,?,?,0,?)',
                            (workspace, watch['id'], event['id'], now()),
                        )
            alerts = [
                dict(r)
                for r in db.execute(
                    'SELECT * FROM alerts WHERE workspace=? ORDER BY created_at DESC', (workspace,)
                )
            ]
        for doc in result['documents']:
            doc['sha256'] = hashlib.sha256(doc['body'].encode()).hexdigest()
        for event in result['events']:
            event['review'] = reviews.get(event['id'], {'status': 'open', 'note': '', 'version': 0})
        return {
            **result,
            'workspace': dict(info),
            'watches': watches,
            'alerts': alerts,
            'history': history,
        }

    def save_review(
        self, workspace: str, event_id: str, status: str, note: str, expected_version: int
    ) -> dict[str, Any]:
        events = snapshot(self.dataset(workspace))['events']
        if event_id not in {e['id'] for e in events}:
            raise KeyError('Detection not found')
        if status not in ('open', 'investigating', 'resolved', 'dismissed'):
            raise ValueError('Unknown review status')
        if not isinstance(note, str) or len(note) > 4000:
            raise ValueError('Note must be text with at most 4000 characters')
        if status in ('resolved', 'dismissed') and not note.strip():
            raise ValueError('A resolution or dismissal needs an explanatory note')
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError('Review version must be a non-negative integer')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute(
                'SELECT version FROM reviews WHERE workspace=? AND event_id=?',
                (workspace, event_id),
            ).fetchone()
            version = existing['version'] if existing else 0
            if version != expected_version:
                raise StaleReview('Review changed in another session; reload before saving')
            updated = now()
            db.execute(
                'INSERT OR REPLACE INTO reviews VALUES (?,?,?,?,?,?)',
                (workspace, event_id, status, note, version + 1, updated),
            )
            db.execute(
                'INSERT INTO history VALUES (NULL,?,?,?,?,?,?)',
                (workspace, event_id, status, note, version + 1, updated),
            )
        return {'status': status, 'note': note, 'version': version + 1, 'updated_at': updated}

    def add_watch(self, workspace: str, label: str, entity_id: str | None, kind: str) -> str:
        data = self.dataset(workspace)
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 100:
            raise ValueError('Watch label must have 1–100 characters')
        if entity_id is not None and entity_id not in {e.id for e in data.entities}:
            raise ValueError('Watch entity not found')
        if kind not in ('all', 'conflict', 'revision', 'addition', 'removal', 'unverified'):
            raise ValueError('Unknown detection type')
        watch = uuid4().hex
        with self.connect() as db:
            db.execute(
                'INSERT INTO watches VALUES (?,?,?,?,?)',
                (watch, workspace, label.strip(), entity_id, kind),
            )
        return watch

    def remove_watch(self, workspace: str, watch_id: str) -> None:
        self.dataset(workspace)
        with self.connect() as db:
            db.execute('DELETE FROM watches WHERE workspace=? AND id=?', (workspace, watch_id))
            db.execute('DELETE FROM alerts WHERE workspace=? AND watch_id=?', (workspace, watch_id))

    def acknowledge(self, workspace: str, watch_id: str, event_id: str) -> None:
        with self.connect() as db:
            cursor = db.execute(
                'UPDATE alerts SET seen=1 WHERE workspace=? AND watch_id=? AND event_id=?',
                (workspace, watch_id, event_id),
            )
            if cursor.rowcount != 1:
                raise KeyError('Alert not found')
