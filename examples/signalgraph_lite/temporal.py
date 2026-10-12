"""Two-clock replay: only observed evidence may affect an asserted validity date."""

from dataclasses import asdict
from itertools import combinations
from typing import Any

from .engine import normalize, resolve
from .models import Dataset, timestamp


def replay(data: Dataset, observed_until: str, valid_at: str) -> dict[str, Any]:
    cutoff, valid = timestamp(observed_until), timestamp(valid_at)
    documents = {d.id: d for d in data.documents if timestamp(d.observed_at) <= cutoff}
    known = [c for c in data.claims if c.source_id in documents]
    rows: list[dict[str, Any]] = []
    for claim in known:
        identity = resolve(claim.entity, data.entities)
        retired_by = [
            c.id for c in known if c.supersedes == claim.id and timestamp(c.valid_from) <= valid
        ]
        if identity is None:
            status = 'ambiguous'
        elif claim.retracted:
            status = 'retraction' if timestamp(claim.valid_from) <= valid else 'future'
        elif timestamp(claim.valid_from) > valid:
            status = 'future'
        elif claim.valid_to and valid >= timestamp(claim.valid_to):
            status = 'expired'
        elif retired_by:
            status = 'superseded'
        else:
            status = 'active'
        rows.append(
            {
                **asdict(claim),
                'entity_id': identity,
                'target_id': resolve(claim.target, data.entities) if claim.target else None,
                'status': status,
                'retired_by': retired_by,
                'observed_at': documents[claim.source_id].observed_at,
            }
        )
    active = [row for row in rows if row['status'] == 'active']
    conflicts = [
        {
            'entity_id': a['entity_id'],
            'predicate': a['predicate'],
            'claim_ids': [a['id'], b['id']],
            'source_ids': [a['source_id'], b['source_id']],
        }
        for a, b in combinations(active, 2)
        if (a['entity_id'], a['predicate']) == (b['entity_id'], b['predicate'])
        and normalize(a['value']) != normalize(b['value'])
    ]
    return {
        'observed_until': observed_until,
        'valid_at': valid_at,
        'document_count': len(documents),
        'known_claim_count': len(known),
        'active_claim_count': len(active),
        'conflicts': conflicts,
        'claims': rows,
        'relationships': [r for r in active if r['target']],
    }
