"""Replay committed real event fixtures offline."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from simulation.replay import EVENT_IDS, replay, write_replay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--event", choices=EVENT_IDS)
    choice.add_argument("--all", action="store_true")
    parser.add_argument("--variant", choices=("grid", "gauges"), default="grid")
    parser.add_argument("--out", default="evidence/replay")
    args = parser.parse_args()
    jobs = [(e, v) for e in EVENT_IDS for v in (("grid", "gauges") if e.startswith("flood")
                                               else ("grid",))] if args.all else [(args.event, args.variant)]
    for event, variant in jobs:
        payload = replay(event, variant)
        path = write_replay(payload, args.out)
        s = payload["summary"]
        print(f"{event} / {variant}: peak {s['peak_score']}; alerts {s['alerts_by_type']}; "
              f"damped nodes {s['damped_nodes']}")
        print(f"  Episodes: {s['node_episodes']} per-node, {s['london_episodes']} London-wide; "
              f"AI firing {s['ai_firing']['flagged']}/{s['ai_firing']['total']} "
              f"({s['ai_firing']['share']:.2%}); quiet {s['quiet_ai_firing']['share']:.2%}")
        q = s["quiet_hours"]
        print(f"  First 6 hours: peak {q['peak_score']}, AI amplified {q['ai_amplified_node_hours']} "
              f"node-hours, alerts {q['alerts_by_type']}. Wrote {path}")
        if variant == "gauges":
            used = [g for g in s["gauges"] if g["used"]]
            print(f"  Rain gauges: {len(used)} used, {len(s['gauges']) - len(used)} excluded; "
                  "all totals, distances and exclusion reasons are in the JSON.")
            for g in used:
                print(f"  {g['label']} -> {g['nearest_node']}: {g['total_mm']} mm, "
                      f"peak {g['peak_hour_mm']} mm at {g['peak_hour']}; {g['distance_km']} km.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
