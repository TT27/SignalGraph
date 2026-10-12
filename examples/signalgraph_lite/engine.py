"""Pure rule-based detection over asserted, single-valued company attributes."""

import json
from collections import defaultdict
from dataclasses import asdict
from itertools import combinations
from pathlib import Path
from typing import Any

from .models import ChangeEvent, Claim, Dataset, Entity, Kind, SourceDocument, timestamp

FIXTURE = Path(__file__).parent / 'fixtures' / 'announcements.json'


def normalize(name: str) -> str:
    return ' '.join(name.casefold().split())


def resolve(name: str, entities: tuple[Entity, ...]) -> str | None:
    # IDs are authoritative. Shared aliases remain ambiguous, never first-match wins.
    if name in {entity.id for entity in entities}:
        return name
    matches = {
        entity.id
        for entity in entities
        if normalize(name) in {normalize(alias) for alias in (entity.name, *entity.aliases)}
    }
    return next(iter(matches)) if len(matches) == 1 else None


def load_dataset(path: Path = FIXTURE) -> Dataset:
    raw = json.loads(path.read_text())
    data = Dataset(
        tuple(Entity(**{**e, 'aliases': tuple(e.get('aliases', []))}) for e in raw['entities']),
        tuple(SourceDocument(**d) for d in raw['documents']),
        tuple(Claim(**c) for c in raw['claims']),
        tuple(raw['periods']),
    )
    validate(data)
    return data


def validate(data: Dataset) -> None:
    for records in (data.entities, data.documents, data.claims):
        ids = [r.id for r in records]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate record IDs')
    if len(data.periods) != 2 or data.periods[0] == data.periods[1]:
        raise ValueError('Exactly two distinct comparison periods required')
    documents = {d.id: d for d in data.documents}
    claims = {c.id: c for c in data.claims}
    for doc in data.documents:
        if doc.period not in data.periods:
            raise ValueError('Unknown source period')
    for claim in data.claims:
        doc = documents.get(claim.source_id)
        if doc is None or not claim.quote or claim.quote not in doc.body:
            raise ValueError(f'Claim {claim.id} must reference an exact source excerpt')
        if claim.target and resolve(claim.target, data.entities) is None:
            raise ValueError('Relationship target must have an unambiguous identity')
        if claim.supersedes:
            prior = claims.get(claim.supersedes)
            if prior is None or prior.id == claim.id:
                raise ValueError('Invalid supersession reference')
            if (resolve(prior.entity, data.entities), prior.predicate) != (
                resolve(claim.entity, data.entities),
                claim.predicate,
            ) or resolve(claim.entity, data.entities) is None:
                raise ValueError('Supersession must concern the same entity and attribute')
            if timestamp(doc.observed_at) <= timestamp(documents[prior.source_id].observed_at):
                raise ValueError('Supersession must be observed after the prior claim')


def overlaps(a: Claim, b: Claim) -> bool:
    start = max(timestamp(a.valid_from), timestamp(b.valid_from))
    ends = [timestamp(c.valid_to) for c in (a, b) if c.valid_to]
    return not ends or start < min(ends)


def detect(data: Dataset) -> list[ChangeEvent]:
    validate(data)
    documents = {d.id: d for d in data.documents}
    claims = {c.id: c for c in data.claims}
    groups: dict[tuple[str, str], list[Claim]] = defaultdict(list)
    events: list[ChangeEvent] = []

    def emit(
        kind: Kind,
        entity: str | None,
        predicate: str,
        before: list[Claim],
        after: list[Claim],
        reason: str,
        classification: str,
    ) -> None:
        evidence = before + after
        sources = tuple(sorted({c.source_id for c in evidence}))
        ids = ':'.join(sorted(c.id for c in evidence))
        events.append(
            ChangeEvent(
                f'{kind}:{ids}',
                kind,
                entity,
                predicate,
                tuple(c.id for c in before),
                tuple(c.id for c in after),
                sources,
                max((documents[s].observed_at for s in sources), key=timestamp),
                f'{reason} Evidence: {", ".join(sources)}.',
                classification,
            )
        )

    for claim in data.claims:
        entity = resolve(claim.entity, data.entities)
        if entity is None:
            emit(
                'unverified',
                None,
                claim.predicate,
                [],
                [claim],
                f'Identity "{claim.entity}" is unknown or ambiguous; comparison withheld',
                'Ambiguous identity',
            )
        else:
            groups[(entity, claim.predicate)].append(claim)

    for (entity, predicate), group in sorted(groups.items()):
        ordered = sorted(group, key=lambda c: (timestamp(documents[c.source_id].observed_at), c.id))
        for a, b in combinations(ordered, 2):
            if a.retracted or b.retracted or normalize(a.value) == normalize(b.value):
                continue
            # An explicit correction retires that assertion for conflict detection.
            if any(c.supersedes == a.id for c in ordered) or any(
                c.supersedes == b.id for c in ordered
            ):
                continue
            if overlaps(a, b):
                emit(
                    'conflict',
                    entity,
                    predicate,
                    [a],
                    [b],
                    'Different values for a single-valued attribute have overlapping validity '
                    'windows; later publication alone does not resolve the conflict',
                    'Conflicting evidence',
                )

        first = [c for c in ordered if documents[c.source_id].period == data.periods[0]]
        second = [c for c in ordered if documents[c.source_id].period == data.periods[1]]
        for current in second:
            prior = claims.get(current.supersedes or '')
            if current.retracted:
                if prior:
                    emit(
                        'removal',
                        entity,
                        predicate,
                        [prior],
                        [current],
                        'The later source explicitly retracts the earlier assertion',
                        'Explicit retraction',
                    )
                else:
                    emit(
                        'unverified',
                        entity,
                        predicate,
                        [],
                        [current],
                        'Retraction has no linked prior assertion',
                        'Incomplete evidence',
                    )
            elif prior:
                if normalize(prior.value) != normalize(current.value):
                    emit(
                        'revision',
                        entity,
                        predicate,
                        [prior],
                        [current],
                        'The later source explicitly supersedes the earlier assertion',
                        'Explicit revision',
                    )
            elif not first:
                emit(
                    'addition',
                    entity,
                    predicate,
                    [],
                    [current],
                    'This attribute is first observed in the later comparison period',
                    'Newly observed assertion',
                )
            else:
                earlier = [c for c in first if not c.retracted]
                if earlier:
                    prior = earlier[-1]
                    if normalize(prior.value) != normalize(current.value) and not overlaps(
                        prior, current
                    ):
                        emit(
                            'revision',
                            entity,
                            predicate,
                            [prior],
                            [current],
                            'Different values apply in non-overlapping validity windows',
                            'Temporal transition',
                        )

        # Absence is not removal. Keep old assertions visible as unverified carry-forwards.
        if first and not second:
            emit(
                'unverified',
                entity,
                predicate,
                first,
                [],
                'No later-period evidence; absence does not establish retraction or continued truth',
                'Not re-observed',
            )
    return sorted(events, key=lambda e: (timestamp(e.observed_at), e.id), reverse=True)


def snapshot(data: Dataset) -> dict[str, Any]:
    events = detect(data)
    relationships = [
        {
            'source': resolve(c.entity, data.entities),
            'target': resolve(c.target, data.entities),
            'predicate': c.predicate,
            'claim_id': c.id,
            'source_id': c.source_id,
            'valid_from': c.valid_from,
            'valid_to': c.valid_to,
            'retracted': c.retracted,
        }
        for c in data.claims
        if c.target
    ]
    return {
        'mode': 'offline-demo',
        'synthetic': True,
        'periods': data.periods,
        'entities': [asdict(e) for e in data.entities],
        'documents': [asdict(d) for d in data.documents],
        'claims': [asdict(c) for c in data.claims],
        'events': [asdict(e) for e in events],
        'relationships': relationships,
        'counts': {
            kind: sum(e.kind == kind for e in events)
            for kind in ('addition', 'removal', 'revision', 'conflict', 'unverified')
        },
    }
