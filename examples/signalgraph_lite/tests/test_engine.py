"""Offline acceptance and temporal edge cases; no Graphiti/LLM dependencies."""

import json
import unittest
from dataclasses import replace
from pathlib import Path

from examples.signalgraph_lite.engine import detect, load_dataset, overlaps, resolve, snapshot
from examples.signalgraph_lite.evaluate import evaluate
from examples.signalgraph_lite.models import Claim, Dataset, Entity, SourceDocument


def comparison(a: Claim, b: Claim) -> Dataset:
    return Dataset(
        (Entity('acme', 'Acme Ltd', 'Company', ('Acme',)),),
        (
            SourceDocument(
                'a', 'Baseline', 'Demo', '2026-01-10T00:00:00Z', 'baseline', a.quote, 'fixture://a'
            ),
            SourceDocument(
                'b', 'Current', 'Demo', '2026-02-10T00:00:00Z', 'current', b.quote, 'fixture://b'
            ),
        ),
        (a, b),
        ('baseline', 'current'),
    )


def pair() -> tuple[Claim, Claim]:
    return (
        Claim('a', 'Acme', 'employees', '10', 'a', 'Acme has 10 staff.', '2026-01-01T00:00:00Z'),
        Claim('b', 'acme', 'employees', '20', 'b', 'Acme has 20 staff.', '2026-02-01T00:00:00Z'),
    )


class DetectionTests(unittest.TestCase):
    def test_labelled_fixture_matches_exact_events(self) -> None:
        data = load_dataset()
        labels = json.loads((Path(__file__).parents[1] / 'fixtures' / 'expected.json').read_text())
        actual = {(e.kind, e.before, e.after) for e in detect(data)}
        expected = {(e['kind'], tuple(e['before']), tuple(e['after'])) for e in labels['events']}
        self.assertEqual(actual, expected)

    def test_acceptance_counts_and_evidence(self) -> None:
        data = load_dataset()
        result = snapshot(data)
        self.assertGreaterEqual(len(data.documents), 8)
        self.assertGreaterEqual(len(data.entities), 5)
        self.assertEqual(result['counts']['conflict'], 2)
        self.assertGreaterEqual(sum(e.kind != 'unverified' for e in detect(data)), 4)
        for event in detect(data):
            self.assertTrue(event.source_ids)
            self.assertTrue(all(s in event.explanation for s in event.source_ids))
        self.assertEqual(json.loads(json.dumps(result))['mode'], 'offline-demo')

    def test_evaluation_is_measured_from_labels(self) -> None:
        self.assertEqual(evaluate()['true_positive'], 8)
        self.assertEqual(evaluate()['precision'], 1.0)
        self.assertEqual(evaluate()['recall'], 1.0)

    def test_overlapping_disagreement_is_conflict_not_revision(self) -> None:
        a, b = pair()
        events = detect(comparison(a, b))
        self.assertEqual([e.kind for e in events], ['conflict'])
        self.assertEqual(events[0].source_ids, ('a', 'b'))

    def test_explicit_correction_is_revision(self) -> None:
        a, b = pair()
        events = detect(comparison(a, replace(b, supersedes='a')))
        self.assertEqual([e.kind for e in events], ['revision'])

    def test_same_value_is_not_a_change(self) -> None:
        a, b = pair()
        self.assertEqual(detect(comparison(a, replace(b, value=' 10 '))), [])

    def test_nonoverlap_is_temporal_revision(self) -> None:
        a, b = pair()
        events = detect(comparison(replace(a, valid_to=b.valid_from), b))
        self.assertEqual([e.kind for e in events], ['revision'])

    def test_half_open_windows_and_timezone_offsets(self) -> None:
        a, b = pair()
        a = replace(a, valid_to='2026-02-01T10:00:00+10:00')
        self.assertFalse(overlaps(a, b))
        self.assertTrue(overlaps(replace(a, valid_to='2026-02-01T10:00:01+10:00'), b))

    def test_observation_order_does_not_override_validity(self) -> None:
        a, b = pair()
        b = replace(b, valid_from='2025-12-01T00:00:00Z')
        event = detect(comparison(a, b))[0]
        self.assertEqual(event.kind, 'conflict')
        self.assertEqual(event.observed_at, '2026-02-10T00:00:00Z')

    def test_removal_requires_explicit_retraction(self) -> None:
        a, b = pair()
        data = comparison(a, b)
        events = detect(replace(data, claims=(a,)))
        self.assertEqual([e.kind for e in events], ['unverified'])
        events = detect(comparison(a, replace(b, retracted=True, supersedes='a')))
        self.assertEqual([e.kind for e in events], ['removal'])

    def test_unlinked_retraction_is_unverified(self) -> None:
        a, b = pair()
        self.assertEqual(
            [e.kind for e in detect(comparison(a, replace(b, retracted=True)))], ['unverified']
        )

    def test_addition_is_first_observation_not_proof_of_creation(self) -> None:
        a, b = pair()
        b = replace(b, predicate='office')
        kinds = {e.kind for e in detect(comparison(a, b))}
        self.assertEqual(kinds, {'addition', 'unverified'})

    def test_ambiguous_alias_is_never_merged(self) -> None:
        data = load_dataset()
        self.assertIsNone(resolve('Nova', data.entities))
        self.assertEqual(resolve(' Nova   Labs ', data.entities), 'nova')
        self.assertEqual(resolve(' NOVA energy ', data.entities), 'nova-energy')
        self.assertIsNone(resolve('Novaa', data.entities))
        self.assertEqual(resolve('nova', data.entities), 'nova')
        ambiguous = [e for e in detect(data) if e.entity_id is None]
        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(ambiguous[0].kind, 'unverified')

    def test_unknown_entity_is_unverified(self) -> None:
        a, b = pair()
        self.assertIn(
            'unverified', [e.kind for e in detect(comparison(a, replace(b, entity='Unknown')))]
        )

    def test_deterministic_with_shuffled_input(self) -> None:
        data = load_dataset()
        self.assertEqual(
            detect(data),
            detect(
                replace(
                    data,
                    claims=tuple(reversed(data.claims)),
                    documents=tuple(reversed(data.documents)),
                )
            ),
        )

    def test_empty_dataset_has_no_detections(self) -> None:
        self.assertEqual(detect(Dataset((), (), (), ('baseline', 'current'))), [])

    def test_invalid_and_naive_timestamps_rejected(self) -> None:
        a, _ = pair()
        for value in ('2026-01-01', 'invalid'):
            with self.assertRaises(ValueError):
                replace(a, valid_from=value)
        with self.assertRaises(ValueError):
            replace(a, valid_to=a.valid_from)

    def test_exact_provenance_required(self) -> None:
        a, b = pair()
        data = comparison(a, b)
        for bad in (replace(b, quote='An invented citation'), replace(b, source_id='missing')):
            with self.assertRaises(ValueError):
                detect(replace(data, claims=(a, bad)))

    def test_duplicate_ids_rejected(self) -> None:
        data = load_dataset()
        with self.assertRaises(ValueError):
            detect(replace(data, claims=data.claims + (data.claims[0],)))

    def test_supersession_timestamp_cannot_precede_original(self) -> None:
        a, b = pair()
        data = comparison(a, replace(b, supersedes='a'))
        documents = (
            data.documents[0],
            replace(data.documents[1], observed_at='2025-12-01T00:00:00Z'),
        )
        with self.assertRaisesRegex(ValueError, 'observed after'):
            detect(replace(data, documents=documents))

    def test_supersession_cannot_change_identity_or_predicate(self) -> None:
        a, b = pair()
        with self.assertRaisesRegex(ValueError, 'same entity'):
            detect(comparison(a, replace(b, supersedes='a', predicate='office')))


if __name__ == '__main__':
    unittest.main()
