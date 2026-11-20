#!/usr/bin/env python3
"""MedLite - tiny offline drug-interaction assistant (compatibility entry point).

The implementation lives in the ``medlite`` package at the repository root.
These commands are identical to ``python3 -m medlite <command>``:

  python3 med.py init                 create med.db with small DEMO data
  python3 med.py load ddinter.csv     import a DDInter CSV (real data) [--release LABEL]
  python3 med.py ask "warfarin and ibuprofen?"  [--llm] [--exact]
  python3 med.py stats                numbers for your report
  python3 med.py serve [--llm] [--port 8000]   web UI at http://127.0.0.1:8000

Information tool only - not medical advice.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, for the medlite package

from medlite import db as _db  # noqa: E402
from medlite.cli import main  # noqa: E402
from medlite.config import Settings  # noqa: E402


def connect():
    """Open the configured database ($MEDLITE_DB, else baseline/med.db)."""
    return _db.connect(Settings.from_env().db_path)


drug_name = _db.drug_name

if __name__ == "__main__":
    main()
