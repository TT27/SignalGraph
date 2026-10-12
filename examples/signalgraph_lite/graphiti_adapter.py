"""Optional Graphiti episode ingestion. External integration is unverified.

Never used by the offline server. The caller supplies a configured Graphiti client;
failures propagate. This adapter does not reinterpret LLM output as demo detections.
"""

import json
from typing import TYPE_CHECKING

from .models import Dataset, timestamp

if TYPE_CHECKING:
    from graphiti_core import Graphiti


async def ingest_episodes(
    client: 'Graphiti', data: Dataset, group_id: str = 'signalgraph-lite-synthetic'
) -> list[str]:
    from graphiti_core.nodes import EpisodeType

    episode_ids: list[str] = []
    for doc in sorted(data.documents, key=lambda d: timestamp(d.observed_at)):
        # reference_time describes source observation; assertion validity stays explicit in JSON.
        body = {
            'source_id': doc.id,
            'observed_at': doc.observed_at,
            'body': doc.body,
            'synthetic': doc.synthetic,
            'claims': [
                {
                    'claim_id': c.id,
                    'quote': c.quote,
                    'entity': c.entity,
                    'predicate': c.predicate,
                    'value': c.value,
                    'valid_from': c.valid_from,
                    'valid_to': c.valid_to,
                    'supersedes': c.supersedes,
                    'retracted': c.retracted,
                    'target': c.target,
                }
                for c in data.claims
                if c.source_id == doc.id
            ],
        }
        result = await client.add_episode(
            name=f'SignalGraph/{doc.id}: {doc.title}',
            episode_body=json.dumps(body),
            source=EpisodeType.json,
            source_description=f'{doc.publisher} | {doc.uri}',
            reference_time=timestamp(doc.observed_at),
            group_id=group_id,
        )
        episode_ids.append(result.episode.uuid)
    return episode_ids
