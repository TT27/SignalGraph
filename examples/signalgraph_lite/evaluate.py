"""Exact-match evaluation on a manually labelled synthetic comparison."""

import json
from pathlib import Path
from typing import Any

from .engine import detect, load_dataset


def signature(event: dict[str, Any]) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    return event['kind'], tuple(sorted(event['before'])), tuple(sorted(event['after']))


def evaluate() -> dict[str, Any]:
    labels = json.loads((Path(__file__).parent / 'fixtures' / 'expected.json').read_text())
    expected = {signature(e) for e in labels['events']}
    actual = {
        (e.kind, tuple(sorted(e.before)), tuple(sorted(e.after))) for e in detect(load_dataset())
    }
    tp = len(expected & actual)
    return {
        'benchmark': 'synthetic-announcements-v1',
        'expected': len(expected),
        'predicted': len(actual),
        'true_positive': tp,
        'false_positive': len(actual - expected),
        'false_negative': len(expected - actual),
        'precision': tp / len(actual) if actual else 0.0,
        'recall': tp / len(expected) if expected else 0.0,
        'limitation': 'Small hand-authored structured fixture; not real-world accuracy.',
    }


if __name__ == '__main__':
    print(json.dumps(evaluate(), indent=2))
