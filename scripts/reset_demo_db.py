"""Reset the Climate Mesh database to a clean state.

Wipes all readings, risk scores, alerts, and run metadata (keeping the schema)
and clears any active demo scenario. Run this before recording a fresh demo so
the dashboard and evidence start from zero.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.database import init_db, reset_db

DEMO_CONTROL_PATH = Path(__file__).parent.parent / "data" / "demo_control.json"


def main() -> int:
    init_db()
    reset_db()
    DEMO_CONTROL_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEMO_CONTROL_PATH.write_text(json.dumps({"scenario": "normal"}))
    print("[reset] Database cleared and scenario reset to 'normal'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
