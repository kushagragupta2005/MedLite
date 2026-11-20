"""Shared fixtures. Tests use synthetic records only: no network, no licensed data."""
import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "baseline"))

from medlite.db import SCHEMA, add_drug, add_interaction, register_source  # noqa: E402
from medlite.demo import load_demo  # noqa: E402

DDINTER_HEADER = ["DDInterID_A", "Drug_A", "DDInterID_B", "Drug_B", "Level"]

# Names shaped like real DDInter entries that the old app matcher could not see.
PUNCTUATED_DRUGS = [
    "anti-inhibitor coagulant complex",
    "amphotericin b",
    "amphotericin b (liposomal)",
    "human botulinum neurotoxin a/b immune globulin",   # more than four tokens
]


def memory_db():
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(SCHEMA)
    return db


def demo_db():
    db = memory_db()
    load_demo(db)
    return db


def punctuated_db():
    """Demo data plus punctuated/long DDInter-style names, each interacting with warfarin."""
    db = demo_db()
    source = register_source(db, "test", "t1", "fixture", "x")
    warfarin = db.execute("SELECT id FROM drug WHERE name='warfarin'").fetchone()[0]
    for index, name in enumerate(PUNCTUATED_DRUGS):
        drug_id = add_drug(db, name)
        add_interaction(db, drug_id, warfarin, ("major", "moderate", "minor", "")[index % 4],
                        "", source, f"fixture-{index}")
    db.commit()
    return db


def drug_id(db, name):
    return db.execute("SELECT id FROM drug WHERE name=?", (name,)).fetchone()[0]


def write_ddinter_csv(path, rows, header=DDINTER_HEADER):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path
