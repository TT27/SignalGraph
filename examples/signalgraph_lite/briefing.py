"""Reproducible, source-linked Markdown briefings and statement diffs, without a model."""

import re
from difflib import SequenceMatcher
from typing import Any


def statement_diff(before: str, after: str) -> list[dict[str, str]]:
    a, b = before.split(), after.split()
    parts = []
    for tag, i, j, k, end in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == 'equal':
            parts.append({'kind': 'equal', 'text': ' '.join(a[i:j])})
        else:
            if i < j:
                parts.append({'kind': 'removed', 'text': ' '.join(a[i:j])})
            if k < end:
                parts.append({'kind': 'added', 'text': ' '.join(b[k:end])})
    return parts


def markdown_text(value: str) -> str:
    # Imported evidence cannot inject executable HTML or fabricated Markdown links.
    for char in ('\\', '`', '*', '_', '[', ']', '<', '>', '#', '|'):
        value = value.replace(char, '\\' + char)
    return value.replace('\r', '').replace('\n', ' ')


def quote_block(value: str) -> str:
    """Keep exact excerpt whitespace inside a fence the excerpt cannot close."""
    longest = max((len(run) for run in re.findall(r'`+', value)), default=0)
    fence = '`' * max(3, longest + 1)
    return f'{fence}text\n{value}\n{fence}'


def briefing(view: dict[str, Any]) -> str:
    entities = {e['id']: e['name'] for e in view['entities']}
    claims = {c['id']: c for c in view['claims']}
    docs = {d['id']: d for d in view['documents']}
    lines = [
        f'# SignalGraph briefing: {markdown_text(view["workspace"]["name"])}',
        '',
        'Deterministic evidence summary. Analyst decisions do not establish factual truth.',
        '',
        f'Data: {"synthetic demo" if view["synthetic"] else "imported local evidence"}. '
        f'{len(docs)} documents, {len(entities)} entities, {len(view["events"])} detections.',
        '',
    ]
    for event in view['events']:
        name = entities.get(event['entity_id'], 'Ambiguous identity')
        lines += [
            f'## {event["kind"].title()}: {markdown_text(name)} / '
            f'{markdown_text(event["predicate"])}',
            '',
            markdown_text(event['explanation']),
            '',
            f'Review: {event["review"]["status"]}. {markdown_text(event["review"]["note"])}',
            '',
        ]
        for side in ('before', 'after'):
            for cid in event[side]:
                c, d = claims[cid], docs[claims[cid]['source_id']]
                lines += [
                    f'{side.title()} ({markdown_text(cid)}):\n\n{quote_block(c["quote"])}\n',
                    f'  Source {markdown_text(d["id"])}: {markdown_text(d["title"])}; '
                    f'observed {d["observed_at"]}; validity {c["valid_from"]} → '
                    f'{c["valid_to"] or "open-ended"}.',
                ]
        lines.append('')
    lines += ['## Source manifest', '']
    for d in view['documents']:
        lines += [
            f'- {markdown_text(d["id"])} — {markdown_text(d["publisher"])}; '
            f'{markdown_text(d["uri"])}; SHA-256 `{d["sha256"]}`'
        ]
    lines += ['', 'Hashes identify stored text; they do not authenticate a publisher.']
    return '\n'.join(lines) + '\n'
