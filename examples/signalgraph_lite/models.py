"""Explicit structured claims; no inferred citations or guessed entity identities."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Kind = Literal['addition', 'removal', 'revision', 'conflict', 'unverified']


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamps must include a timezone')
    return parsed


@dataclass(frozen=True)
class Entity:
    id: str
    name: str
    kind: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceDocument:
    id: str
    title: str
    publisher: str
    observed_at: str
    period: str
    body: str
    uri: str
    synthetic: bool = True

    def __post_init__(self) -> None:
        timestamp(self.observed_at)


@dataclass(frozen=True)
class Claim:
    id: str
    entity: str
    predicate: str
    value: str
    source_id: str
    quote: str
    valid_from: str
    valid_to: str | None = None
    target: str | None = None
    retracted: bool = False
    supersedes: str | None = None

    def __post_init__(self) -> None:
        start = timestamp(self.valid_from)
        if self.valid_to is not None and timestamp(self.valid_to) <= start:
            raise ValueError('Validity windows are half-open and must have positive duration')


@dataclass(frozen=True)
class ChangeEvent:
    id: str
    kind: Kind
    entity_id: str | None
    predicate: str
    before: tuple[str, ...]
    after: tuple[str, ...]
    source_ids: tuple[str, ...]
    observed_at: str
    explanation: str
    classification: str


@dataclass(frozen=True)
class Dataset:
    entities: tuple[Entity, ...]
    documents: tuple[SourceDocument, ...]
    claims: tuple[Claim, ...]
    periods: tuple[str, str]
