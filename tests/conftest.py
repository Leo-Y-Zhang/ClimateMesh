"""Shared pytest fixtures.

Every test runs against an isolated SQLite file (never the demo DB), and the
AI detector is trained once per session for speed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Make the project importable and pin the DB to a temp file before any import
# of data.database resolves a path.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session", autouse=True)
def _isolated_db(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "test_climate_mesh.db"
    os.environ["CLIMATE_MESH_DB"] = str(db_path)
    from data.database import init_db
    init_db()
    yield
    from data.database import close
    close()


@pytest.fixture(autouse=True)
def _clean_db():
    """Reset all tables before each test for isolation."""
    from data.database import init_db, reset_db
    init_db()
    reset_db()
    yield


@pytest.fixture(scope="session")
def detector():
    from ai.anomaly_model import AnomalyDetector
    return AnomalyDetector().train(quiet=True)
