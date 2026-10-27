"""Summarise recorded calibration evidence and list every held-out alert."""
from __future__ import annotations

import csv
import gzip
import io
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np

from config.nodes import ENVIRONMENTS
from ai.anomaly_model import FEATURES, AnomalyDetector, _rows_from_archive
from backend.risk_engine import calculate_base, compute_all, risk_level
from sensors.simulated_adapter import SimulatedAdapter
from simulation.replay import EVENT_IDS, ROOT
from simulation.replay_io import alert_metrics, episode_annotations, read_json, write_json

OUT = ROOT / 'evidence' / 'replay'
HAZARD_SUBS = {'heatwave': ('temp_sub',), 'cold': ('temp_sub',),
               'flood': ('water_sub',), 'smog': ('aqi_sub',),
               'storm': ('wind_sub',), 'risk': ()}
CLASSES = ('hazard-alone', 'multiplier-dependent')


def alert_class(row, version="calibrated"):
    """Predeclared WARNING rule: the driving hazard alone must contribute >=60.

    Secondary terms and multipliers never count as direct hazard evidence.
    The second class follows this fixed rule; combined secondary terms can
    already cross WARNING before multiplication, so it is not a truth label.
    Sensor-checks retain the underlying dominant hazard for this classification.
    """
    keys = HAZARD_SUBS[row['dominant_hazard']]
    if row['dominant_hazard'] == 'storm' and version != 'calibrated':
        keys = ('wind_sub', 'pressure_sub')
    driving = max((row[k] for k in keys), default=0)
    return CLASSES[0] if driving >= 60 else CLASSES[1]


def metrics(payload, version="calibrated"):
    quiet = [r for h in payload['per_hour'][:6] for r in h['nodes']]
    all_rows = [r for h in payload['per_hour'] for r in h['nodes']]
    counts = Counter(alert_class(r, version) for r in all_rows if r['alert'])
    quiet_counts = Counter(alert_class(r, version) for r in quiet if r['alert'])
    return {
        **alert_metrics(payload['per_hour']),
        'drivers': driver_distributions(all_rows),
        'peak_score': payload['summary']['peak_score'],
        'alerts_by_type': payload['summary']['alerts_by_type'],
        'quiet_alerts': sum(bool(r['alert']) for r in quiet),
        'quiet_peak': payload['summary']['quiet_hours']['peak_score'],
        'quiet_ai_flags': sum(r['ai_multiplier'] > 1 for r in quiet),
        'quiet_alert_classes': {c: quiet_counts[c] for c in CLASSES},
        'alert_classes': {c: counts[c] for c in CLASSES},
        'quiet_ai_by_environment': {
            env: {'flagged': sum(r['ai_multiplier'] > 1 for r in quiet if r['environment'] == env),
                  'total': sum(r['environment'] == env for r in quiet)} for env in ENVIRONMENTS},
        'event_hazard_alerts': sum(r['alert'] == {
            'flood': 'flood', 'heat': 'heatwave', 'storm': 'storm'
        }.get(payload['event_id'].split('-')[0]) for r in all_rows if r['alert']),
    }


def driver_distributions(rows):
    result = {}
    for hazard, field, divisor in (('smog', 'air_quality', 2.5), ('cold', 'temperature', 1),
                                    ('storm', 'wind_speed', 1)):
        values = [r[field] / divisor for r in rows if r['alert'] == hazard]
        if values:
            result[hazard] = dict(zip(('min', 'p25', 'median', 'p75', 'max'),
                                     np.round(np.percentile(values, [0, 25, 50, 75, 100]), 3).tolist()))
    return result


def feature_diagnostics(fixture, payload):
    training = fixture['training']
    fitted = _rows_from_archive(training['weather'], training['air'])
    served = np.asarray([[r[f] for f in FEATURES] for step in payload['per_hour'] for r in step['nodes']])
    return {feature: {
        'train_range': [float(fitted[:, j].min()), float(fitted[:, j].max())],
        'replay_range': [float(served[:, j].min()), float(served[:, j].max())],
        'outside_training_share': float(np.mean((served[:, j] < fitted[:, j].min()) |
                                                (served[:, j] > fitted[:, j].max()))),
    } for j, feature in enumerate(FEATURES)}


def main():
    report, alerts, diagnostics = {}, [], {}
    for event in EVENT_IDS:
        fixture = read_json(ROOT / 'data' / 'history' / f'{event}.json')
        training = fixture['training']['weather']['hourly']
        humidity, pressure = training['relative_humidity_2m'], training['pressure_msl']
        for variant in ('grid', 'gauges') if event.startswith('flood') else ('grid',):
            name = f'{event}-{variant}'
            entry = {'rh_ge_85': sum(v >= 85 for v in humidity), 'training_hours': len(humidity),
                     'pressure_le_1000': sum(v <= 1000 for v in pressure)}
            stages = [('as_found', OUT / 'as-found')]
            if '2024' not in event:
                stages.append(('round_1', OUT / 'round-1'))
            stages.append(('calibrated', OUT))
            for label, directory in stages:
                payload = read_json(directory / f'{name}.json')
                entry[label] = metrics(payload, label)
                if label == 'calibrated' and variant == 'grid':
                    diagnostics[event] = feature_diagnostics(fixture, payload)
                annotations = episode_annotations(payload['per_hour'])
                if not event.startswith('holdout'):
                    continue
                for hour_index, h in enumerate(payload['per_hour']):
                    for r in h['nodes']:
                        if not r['alert']:
                            continue
                        fields = ('node_id', 'dominant_hazard', 'alert', 'score', 'band',
                                  'temperature', 'humidity', 'air_quality', 'water_level',
                                  'wind_speed', 'barometric_pressure', 'temp_sub', 'humidity_sub',
                                  'aqi_sub', 'water_sub', 'wind_sub', 'pressure_sub',
                                  'ai_multiplier', 'mesh_multiplier', 'corroboration')
                        arrays = fixture['nodes'][r['node_id']]
                        running_rain = sum(arrays['precipitation'][j] for j in range(hour_index + 1)
                                           if fixture['hours'][j][:10] == h['hour'][:10])
                        alerts.append({'version': label, 'event': event, 'hour': h['hour'],
                                       'class': alert_class(r, label), **{k: r[k] for k in fields},
                                       'eaqi': arrays['european_aqi'][hour_index],
                                       'is_anomaly': r.get('is_anomaly', r['ai_multiplier'] > 1),
                                       **annotations[(h['hour'], r['node_id'])],
                                       'hourly_rain_mm': arrays['precipitation'][hour_index],
                                       'rain_since_midnight_mm': round(running_rain, 3)})
            report[name] = entry
    write_json(report, OUT / 'calibration-summary.json')
    write_json(diagnostics, OUT / 'ai-feature-diagnostics.json')
    alerts.sort(key=lambda r: (r['version'], r['event'], r['class'], r['hour'], r['node_id']))
    path = OUT / 'held-out-alerts.csv.gz'
    with path.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as zipped:
        with io.TextIOWrapper(zipped, encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(alerts[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(alerts)
    (OUT / 'held-out-alerts.csv').unlink(missing_ok=True)
    detector = AnomalyDetector().train(quiet=True)
    ablation = {}
    for scenario in ('normal', 'flood', 'heatwave', 'smog', 'storm'):
        readings = SimulatedAdapter(demo=True).read_all(scenario, tick=0.0)
        ablation[scenario] = {
            'sub_scores': dict(Counter(risk_level(calculate_base(r, detector)['base_score'])
                                       for r in readings)),
            'full': dict(Counter(r['level'] for r in compute_all(readings, detector))),
        }
    write_json(ablation, OUT / 'ablation.json')
    for event, entry in report.items():
        print(event)
        for version in ('as_found', 'round_1', 'calibrated'):
            if version not in entry:
                continue
            m = entry[version]
            print(f"  {version}: {m['alert_hours']} alert-hours, {m['node_episodes']} node episodes, "
                  f"{m['london_episodes']} London episodes; AI {m['ai_firing']}; quiet AI {m['quiet_ai_firing']}")
    print(f'Listed {len(alerts)} held-out alerts with readings and episode IDs')


if __name__ == '__main__':
    main()
