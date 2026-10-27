"""Replay the verified baseline source snapshot and preserved fixtures offline."""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from simulation.replay_io import enrich_replay, read_json, write_json
BASE = ROOT / "evidence" / "replay" / "as-found"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="separate output directory")
    parser.add_argument('--capture-new', action='store_true',
                        help='capture only missing replay outputs for newly supplied snapshot fixtures')
    args = parser.parse_args()
    out = args.out.resolve()
    if out == BASE or BASE in out.parents:
        parser.error("output must not overwrite the preserved evidence")
    archive = (BASE / "source.tar.gz").read_bytes()
    jobs = sorted(p.name.removesuffix('.gz') for p in BASE.glob("*.json*")
                  if p.name.removesuffix('.gz').endswith(("-grid.json", "-gauges.json")))
    if args.capture_new:
        for fixture in sorted((BASE / 'fixtures').glob('holdout-2024-*.json.gz')):
            name = fixture.name.removesuffix('.json.gz') + '-grid.json'
            if name not in jobs:
                jobs.append(name)
        jobs.sort()
    # Extract only Python source from the local snapshot. Fixture observations
    # are preserved separately, including the predeclared test-year windows.
    with tempfile.TemporaryDirectory(prefix=".as-found-", dir=ROOT) as temporary:
        source = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            for member in tar:
                name = PurePosixPath(member.name)
                if not member.isfile() or name.suffix != ".py":
                    continue
                if name.is_absolute() or ".." in name.parts:
                    raise ValueError("unexpected archive path")
                path = source / member.name
                path.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as stream, path.open("wb") as target:
                    shutil.copyfileobj(stream, target)
        fixtures = source / "data" / "history"
        fixtures.mkdir(parents=True, exist_ok=True)
        for path in (BASE / "fixtures").glob("*.json*"):
            write_json(read_json(path), fixtures / path.name.removesuffix('.gz'))
        runner = '''
import json, sys
from pathlib import Path
from simulation import replay
out, jobs = Path(sys.argv[1]), json.loads(sys.argv[2])
replay.EVENT_IDS = tuple(name.rsplit('-', 1)[0] for name in jobs)
for name in jobs:
    event, variant = name[:-5].rsplit('-', 1)
    replay.write_replay(replay.replay(event, variant), out)
'''
        env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"}
        subprocess.run([sys.executable, "-c", runner, str(out), json.dumps(jobs)],
                       cwd=source, env=env, check=True)
    for name in jobs:
        original = out / name
        payload = enrich_replay(read_json(original))
        target = out / (name + '.gz')
        write_json(payload, target)
        original.unlink()
        preserved = BASE / target.name
        if args.capture_new and not preserved.exists():
            preserved.write_bytes(target.read_bytes())
        if target.read_bytes() != preserved.read_bytes():
            raise ValueError(f"baseline differs: {name}; use the recorded dependency versions")
    print(f"PASS: {len(jobs)} original-code replays reproduce the preserved JSONs byte for byte")


if __name__ == "__main__":
    main()
