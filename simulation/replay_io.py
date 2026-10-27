"""Compact, reproducible replay storage and sampled alert diagnostics."""
from __future__ import annotations

import gzip
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path


def read_json(path):
    """Read plain JSON or its .gz counterpart (including historical fixtures)."""
    path = Path(path)
    if not path.exists() and path.suffix != '.gz':
        path = Path(str(path) + '.gz')
    data = gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes()
    return json.loads(data)


def write_json(payload, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
    if path.suffix == '.gz':
        # gzip.compress's OS byte varies across Python/zlib versions; GzipFile
        # also guarantees no original filename is embedded in the header.
        with path.open('wb') as stream, gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as zipped:
            zipped.write(data)
    else:
        path.write_bytes(data)
    return path


def episode_annotations(per_hour):
    """Return node/London episode IDs and start flags for each alert row.

    Episodes follow delivered alert types, including sensor-check. A missing
    sample, a nonalert hour or a changed hazard breaks a node episode. London
    runs continue when the alerting node changes but the hazard stays present.
    """
    previous_nodes, previous_london, previous_time = {}, {}, None
    annotations = {}
    for step in per_hour:
        instant = datetime.fromisoformat(step['hour'])
        consecutive = previous_time is not None and instant - previous_time == timedelta(hours=1)
        nodes, london = {}, {}
        for row in step['nodes']:
            hazard = row['alert']
            if not hazard:
                continue
            node = row['node_id']
            old_node = previous_nodes.get((node, hazard)) if consecutive else None
            old_london = previous_london.get(hazard) if consecutive else None
            node_id = old_node or f"{hazard}:{node}:{step['hour']}"
            london_id = old_london or f"{hazard}:{step['hour']}"
            annotations[(step['hour'], node)] = {
                'node_episode': node_id, 'london_episode': london_id,
                'node_episode_start': int(old_node is None),
                'london_episode_start': int(old_london is None and hazard not in london),
            }
            nodes[(node, hazard)], london[hazard] = node_id, london_id
        previous_nodes, previous_london, previous_time = nodes, london, instant
    return annotations


def alert_metrics(per_hour):
    annotations = episode_annotations(per_hour)
    hours, nodes, london = Counter(), Counter(), Counter()
    rows = [r for h in per_hour for r in h['nodes']]
    quiet = [r for h in per_hour[:6] for r in h['nodes']]
    for step in per_hour:
        for row in step['nodes']:
            if row['alert']:
                item = annotations[(step['hour'], row['node_id'])]
                hours[row['alert']] += 1
                nodes[row['alert']] += item['node_episode_start']
                london[row['alert']] += item['london_episode_start']

    def ai_rate(samples):
        flagged = sum(r.get('is_anomaly', r['ai_multiplier'] > 1) for r in samples)
        return {'flagged': flagged, 'total': len(samples),
                'share': flagged / len(samples) if samples else 0.0}

    return {'alert_hours': sum(hours.values()), 'node_episodes': sum(nodes.values()),
            'london_episodes': sum(london.values()),
            'by_hazard': {hazard: {'alert_hours': hours[hazard], 'node_episodes': nodes[hazard],
                                   'london_episodes': london[hazard]} for hazard in sorted(hours)},
            'ai_firing': ai_rate(rows), 'quiet_ai_firing': ai_rate(quiet)}


def enrich_replay(payload):
    payload['summary'].update(alert_metrics(payload['per_hour']))
    return payload
