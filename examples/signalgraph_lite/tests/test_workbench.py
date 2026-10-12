"""Temporal correctness and durable analyst workflows against disposable SQLite stores."""

import hashlib
import json
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from examples.signalgraph_lite.briefing import briefing, quote_block, statement_diff
from examples.signalgraph_lite.engine import dataset_from_dict, load_dataset
from examples.signalgraph_lite.store import StaleReview, WorkspaceStore
from examples.signalgraph_lite.temporal import replay


def payload() -> dict:
    return json.loads(json.dumps(asdict(load_dataset())))


class ReplayTests(unittest.TestCase):
    def test_future_publications_do_not_leak(self) -> None:
        state = replay(load_dataset(), '2026-01-20T23:00:00Z', '2026-02-12T00:00:00Z')
        self.assertEqual(state['document_count'], 5)
        self.assertNotIn('c07', {c['id'] for c in state['claims']})
        self.assertIn('c02', {c['id'] for c in state['claims'] if c['status'] == 'active'})
        self.assertEqual(state['conflicts'], [])

    def test_known_revision_applies_only_after_its_validity_start(self) -> None:
        data = load_dataset()
        earlier = replay(data, '2026-02-20T00:00:00Z', '2026-01-20T00:00:00Z')
        later = replay(data, '2026-02-20T00:00:00Z', '2026-02-12T00:00:00Z')
        before = {c['id']: c['status'] for c in earlier['claims']}
        after = {c['id']: c['status'] for c in later['claims']}
        self.assertEqual(before['c02'], 'active')
        self.assertEqual(before['c07'], 'future')
        self.assertEqual(after['c02'], 'superseded')
        self.assertEqual(after['c07'], 'active')
        self.assertEqual(before['c05'], 'active')
        self.assertEqual(after['c05'], 'superseded')
        self.assertEqual(after['c10'], 'retraction')

    def test_expired_half_open_window_is_not_active(self) -> None:
        state = replay(load_dataset(), '2026-02-20T00:00:00Z', '2026-02-01T00:00:00Z')
        self.assertEqual(next(c['status'] for c in state['claims'] if c['id'] == 'c01'), 'expired')

    def test_conflicts_require_both_observation_and_validity(self) -> None:
        state = replay(load_dataset(), '2026-02-20T00:00:00Z', '2026-02-12T00:00:00Z')
        self.assertEqual(len(state['conflicts']), 2)
        expired = replay(load_dataset(), '2026-02-20T00:00:00Z', '2026-04-01T00:00:00Z')
        self.assertEqual(len(expired['conflicts']), 1)

    def test_observation_offsets_compare_as_instants(self) -> None:
        a = replay(load_dataset(), '2026-01-05T19:00:00+10:00', '2026-01-06T00:00:00Z')
        b = replay(load_dataset(), '2026-01-05T09:00:00Z', '2026-01-06T00:00:00Z')
        self.assertEqual(a['claims'], b['claims'])

    def test_unknown_alias_is_never_active(self) -> None:
        state = replay(load_dataset(), '2026-02-20T00:00:00Z', '2026-02-12T00:00:00Z')
        self.assertEqual(
            next(c['status'] for c in state['claims'] if c['id'] == 'c12'), 'ambiguous'
        )

    def test_no_observed_data_is_explicitly_empty(self) -> None:
        state = replay(load_dataset(), '2025-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
        self.assertEqual(state['known_claim_count'], 0)


class PersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'workspace.sqlite3'
        self.store = WorkspaceStore(self.path)
        self.event = self.store.view('demo')['events'][0]['id']

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_import_is_separate_and_labels_are_preserved(self) -> None:
        source = payload()
        for doc in source['documents']:
            doc['synthetic'] = False
        workspace = self.store.import_dataset('Supplier investigation', source)
        result = self.store.view(workspace)
        self.assertEqual(result['mode'], 'local-workspace')
        self.assertFalse(result['synthetic'])
        self.assertTrue(self.store.view('demo')['synthetic'])
        self.assertEqual(len(self.store.list_workspaces()), 2)

    def test_bad_import_rolls_back(self) -> None:
        source = payload()
        source['claims'][0]['quote'] = 'fabricated'
        with self.assertRaises(ValueError):
            self.store.import_dataset('Bad', source)
        self.assertEqual(len(self.store.list_workspaces()), 1)

    def test_review_survives_restart_with_append_only_history(self) -> None:
        self.store.save_review('demo', self.event, 'investigating', 'Check source', 0)
        restarted = WorkspaceStore(self.path)
        review = next(
            e['review'] for e in restarted.view('demo')['events'] if e['id'] == self.event
        )
        self.assertEqual(review['note'], 'Check source')
        restarted.save_review('demo', self.event, 'resolved', 'Publisher clarified.', 1)
        self.assertEqual(len(restarted.view('demo')['history']), 2)

    def test_stale_review_cannot_overwrite_notes(self) -> None:
        self.store.save_review('demo', self.event, 'investigating', 'First analyst', 0)
        with self.assertRaises(StaleReview):
            self.store.save_review('demo', self.event, 'dismissed', 'Stale analyst', 0)
        self.assertEqual(self.store.view('demo')['history'][0]['note'], 'First analyst')

    def test_resolution_needs_rationale(self) -> None:
        for status in ('resolved', 'dismissed'):
            with self.assertRaises(ValueError):
                self.store.save_review('demo', self.event, status, '', 0)

    def test_analyst_resolution_does_not_delete_conflicting_evidence(self) -> None:
        before = self.store.view('demo')
        conflict = next(e for e in before['events'] if e['kind'] == 'conflict')
        self.store.save_review(
            'demo', conflict['id'], 'resolved', 'Reviewed; source B is stale.', 0
        )
        after = self.store.view('demo')
        self.assertEqual(before['counts'], after['counts'])
        self.assertEqual(before['claims'], after['claims'])
        self.assertEqual(before['documents'], after['documents'])

    def test_reviews_are_isolated_between_investigations(self) -> None:
        other = self.store.import_dataset('Other', payload())
        self.store.save_review('demo', self.event, 'investigating', 'Private to demo', 0)
        self.assertFalse(self.store.view(other)['history'])

    def test_watch_alerts_deduplicate_and_acknowledgement_persists(self) -> None:
        watch = self.store.add_watch('demo', 'Revenue conflicts', 'helios', 'conflict')
        first = self.store.view('demo')['alerts']
        self.assertEqual(len(first), 1)
        self.assertEqual(first, self.store.view('demo')['alerts'])
        self.store.acknowledge('demo', watch, first[0]['event_id'])
        self.assertEqual(WorkspaceStore(self.path).view('demo')['alerts'][0]['seen'], 1)
        self.store.remove_watch('demo', watch)
        self.assertFalse(self.store.view('demo')['alerts'])

    def test_watch_rejects_unknown_entity(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_watch('demo', 'Bad watch', 'unknown', 'conflict')

    def test_identical_append_is_idempotent(self) -> None:
        workspace = self.store.import_dataset('Appendable', payload())
        self.store.append_dataset(workspace, payload())
        self.assertEqual(len(self.store.dataset(workspace).documents), 12)

    def test_append_refuses_to_rewrite_original_evidence(self) -> None:
        workspace = self.store.import_dataset('Appendable', payload())
        changed = payload()
        changed['documents'][0]['title'] = 'Rewritten'
        with self.assertRaisesRegex(ValueError, 'Immutable'):
            self.store.append_dataset(workspace, changed)
        self.assertEqual(self.store.dataset(workspace), load_dataset())

    def test_demo_is_not_mutable_by_append(self) -> None:
        with self.assertRaises(ValueError):
            self.store.append_dataset('demo', payload())

    def test_appended_evidence_generates_new_alert_once(self) -> None:
        workspace = self.store.import_dataset('Appendable', payload())
        self.store.add_watch(workspace, 'All revisions', None, 'revision')
        self.assertEqual(len(self.store.view(workspace)['alerts']), 2)
        data = load_dataset()
        doc = replace(
            data.documents[-1],
            id='s13',
            observed_at='2026-02-20T09:00:00Z',
            body='Atlas Cloud now operates globally.',
        )
        claim = replace(
            data.claims[-1],
            id='c14',
            source_id='s13',
            quote=doc.body,
            value='Global',
            valid_from='2026-02-20T00:00:00Z',
            supersedes='c13',
        )
        updated = replace(data, documents=data.documents + (doc,), claims=data.claims + (claim,))
        self.store.append_dataset(workspace, json.loads(json.dumps(asdict(updated))))
        self.assertEqual(len(self.store.view(workspace)['alerts']), 3)
        self.assertEqual(len(self.store.view(workspace)['alerts']), 3)

    def test_manifest_hash_identifies_exact_stored_text(self) -> None:
        doc = self.store.view('demo')['documents'][0]
        self.assertEqual(doc['sha256'], hashlib.sha256(doc['body'].encode()).hexdigest())

    def test_briefing_contains_review_provenance_and_all_evidence(self) -> None:
        self.store.save_review('demo', self.event, 'investigating', 'Needs follow-up', 0)
        text = briefing(self.store.view('demo'))
        self.assertIn('Needs follow-up', text)
        self.assertIn('SHA-256', text)
        self.assertIn('fixture://announcements/s01', text)
        self.assertIn('overlapping validity', text)
        self.assertEqual(text, briefing(self.store.view('demo')))

    def test_markdown_neutralizes_imported_html_and_links(self) -> None:
        source = payload()
        source['documents'][0]['title'] = '<script>alert(1)</script> [link](javascript:evil)'
        workspace = self.store.import_dataset('Safety', source)
        text = briefing(self.store.view(workspace))
        self.assertNotIn('<script>', text)
        self.assertNotIn('[link]', text)


class ImportValidationTests(unittest.TestCase):
    def test_delimited_ids_cannot_collide_with_event_signatures(self) -> None:
        source = payload()
        source['claims'][0]['id'] = 'a:b'
        with self.assertRaisesRegex(ValueError, 'IDs must'):
            dataset_from_dict(source)

    def test_export_preserves_literal_multiline_quote_and_fences(self) -> None:
        quote = 'First line.\n```html\n<script>example</script>'
        rendered = quote_block(quote)
        self.assertIn(quote, rendered)
        self.assertTrue(rendered.startswith('````text\n'))

    def test_malformed_types_cannot_be_coerced_into_claims(self) -> None:
        for field, value in [('value', 150), ('retracted', 'false'), ('valid_from', [])]:
            source = payload()
            source['claims'][0][field] = value
            with self.assertRaises(ValueError):
                dataset_from_dict(source)

    def test_sources_need_explicit_synthetic_classification(self) -> None:
        source = payload()
        del source['documents'][0]['synthetic']
        with self.assertRaisesRegex(ValueError, 'synthetic'):
            dataset_from_dict(source)

    def test_word_diff_preserves_both_values(self) -> None:
        parts = statement_diff('Revenue is USD 20m for Q1.', 'Revenue is USD 28m for Q1.')
        self.assertIn({'kind': 'removed', 'text': '20m'}, parts)
        self.assertIn({'kind': 'added', 'text': '28m'}, parts)
        self.assertEqual(statement_diff('', ''), [])
