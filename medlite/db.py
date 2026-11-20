"""SQLite schema, connection and write helpers. The database is the source of truth."""
import sqlite3

SEVERITIES = ("major", "moderate", "minor", "unknown")
SEVERITY_RANK = {name: rank for rank, name in enumerate(SEVERITIES)}
SEV_ORDER_SQL = "CASE severity WHEN 'major' THEN 0 WHEN 'moderate' THEN 1 WHEN 'minor' THEN 2 ELSE 3 END"

SCHEMA = """
CREATE TABLE IF NOT EXISTS drug(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS alias(alias TEXT PRIMARY KEY, drug_id INTEGER NOT NULL REFERENCES drug(id));
CREATE TABLE IF NOT EXISTS data_source(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, release TEXT NOT NULL,
  imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, source_file TEXT NOT NULL,
  sha256 TEXT NOT NULL, source_url TEXT, license_note TEXT,
  UNIQUE(name, release, source_file, sha256));
CREATE TABLE IF NOT EXISTS interaction(
  a INTEGER NOT NULL REFERENCES drug(id), b INTEGER NOT NULL REFERENCES drug(id),
  severity TEXT NOT NULL CHECK(severity IN ('major','moderate','minor','unknown')),
  note TEXT, source_id INTEGER REFERENCES data_source(id), source_record_id TEXT,
  PRIMARY KEY(a, b), CHECK(a < b));
CREATE INDEX IF NOT EXISTS ix_interaction_b ON interaction(b);
CREATE TABLE IF NOT EXISTS log(id INTEGER PRIMARY KEY, ts TEXT DEFAULT CURRENT_TIMESTAMP,
  question TEXT, found TEXT, answer TEXT);
"""


def connect(path):
    """Open (creating if needed) a MedLite database and apply in-place migrations."""
    db = sqlite3.connect(str(path))
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(SCHEMA)
    _migrate(db)
    return db


def _migrate(db):
    # Databases created before provenance tracking lack these columns.
    columns = {row[1] for row in db.execute("PRAGMA table_info(interaction)")}
    if "source_id" not in columns:
        db.execute("ALTER TABLE interaction ADD COLUMN source_id INTEGER REFERENCES data_source(id)")
    if "source_record_id" not in columns:
        db.execute("ALTER TABLE interaction ADD COLUMN source_record_id TEXT")


def register_source(db, name, release, source_file, sha256, source_url=None, license_note=None):
    db.execute("""INSERT OR IGNORE INTO data_source
                  (name, release, source_file, sha256, source_url, license_note)
                  VALUES(?,?,?,?,?,?)""",
               (name, release, source_file, sha256, source_url, license_note))
    return db.execute("""SELECT id FROM data_source
                         WHERE name=? AND release=? AND source_file=? AND sha256=?""",
                      (name, release, source_file, sha256)).fetchone()[0]


def add_drug(db, name, aliases=()):
    name = name.strip().lower()
    db.execute("INSERT OR IGNORE INTO drug(name) VALUES(?)", (name,))
    drug_id = db.execute("SELECT id FROM drug WHERE name=?", (name,)).fetchone()[0]
    for alias in (name, *aliases):
        db.execute("INSERT OR IGNORE INTO alias VALUES(?,?)", (alias.strip().lower(), drug_id))
    return drug_id


def normalize_severity(value):
    value = (value or "").strip().lower()
    return value if value in ("major", "moderate", "minor") else "unknown"


def add_interaction(db, id_a, id_b, severity, note="", source_id=None, source_record_id=None):
    if id_a == id_b:
        return
    a, b = sorted((id_a, id_b))
    db.execute("""INSERT OR REPLACE INTO interaction
                  (a, b, severity, note, source_id, source_record_id)
                  VALUES(?,?,?,?,?,?)""",
               (a, b, normalize_severity(severity), note, source_id, source_record_id))


def drug_name(db, drug_id):
    return db.execute("SELECT name FROM drug WHERE id=?", (drug_id,)).fetchone()[0]


def drug_names(db, drug_ids):
    """Map ids to names with one query instead of one query per id."""
    ids = list(dict.fromkeys(drug_ids))
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    return dict(db.execute(f"SELECT id, name FROM drug WHERE id IN ({marks})", ids))


def drug_count(db):
    return db.execute("SELECT COUNT(*) FROM drug").fetchone()[0]
