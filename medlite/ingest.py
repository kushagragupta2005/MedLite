"""Import DDInter CSV exports with file-level provenance."""
import csv
import hashlib
import os
import re
from dataclasses import dataclass

from .db import add_drug, add_interaction, register_source

DDINTER_URL = "https://ddinter.scbdd.com/download/"
DDINTER_LICENSE = ("DDInter CC BY-NC-SA 4.0; attribution, noncommercial use, and share-alike terms apply; "
                   "see https://ddinter.scbdd.com/terms/.")

# Brand/alternate names -> generic name as DDInter spells it (lowercase).
BRAND_ALIASES = {
    "acetaminophen": ["paracetamol", "crocin", "dolo", "calpol", "tylenol"],
    "acetylsalicylic acid": ["aspirin", "ecosprin", "disprin"],
    "ibuprofen": ["brufen", "advil", "motrin"],
    "metformin": ["glycomet", "glucophage"],
    "warfarin": ["coumadin"], "simvastatin": ["zocor"], "atorvastatin": ["lipitor"],
    "amlodipine": ["norvasc"], "fluoxetine": ["prozac"], "clopidogrel": ["plavix"],
    "omeprazole": ["prilosec"], "sildenafil": ["viagra"],
}


class ImportFormatError(ValueError):
    """The CSV does not look like a DDInter interaction export."""


@dataclass(frozen=True)
class ImportResult:
    rows: int
    drugs: int
    sha256: str
    missing_alias_targets: tuple


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as raw:
        for block in iter(lambda: raw.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _find_columns(headers):
    low = {column: column.lower().replace(" ", "_") for column in headers}

    def first(predicate):
        return next((column for column in headers if predicate(low[column])), None)

    return {
        "a": first(lambda c: re.fullmatch(r"drug(name)?_?(name_)?a", c)),
        "b": first(lambda c: re.fullmatch(r"drug(name)?_?(name_)?b", c)),
        "id_a": first(lambda c: c in ("ddinterid_a", "drug_id_a", "id_a")),
        "id_b": first(lambda c: c in ("ddinterid_b", "drug_id_b", "id_b")),
        "level": first(lambda c: "level" in c or "sever" in c),
    }


def add_brand_aliases(db, aliases=None):
    """Attach brand names to generics present in the data; return generics that were absent."""
    missing = []
    for generic, brands in (aliases or BRAND_ALIASES).items():
        row = db.execute("SELECT id FROM drug WHERE name=?", (generic,)).fetchone()
        if not row:
            missing.append(generic)
            continue
        for brand in brands:
            db.execute("INSERT OR IGNORE INTO alias VALUES(?,?)", (brand, row[0]))
    return tuple(missing)


def load_ddinter_csv(db, path, release="unspecified", source_url=DDINTER_URL, license_note=DDINTER_LICENSE):
    """Import one DDInter CSV, recording its SHA-256, release label and per-row DDInter IDs."""
    digest = file_sha256(path)
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = _find_columns(reader.fieldnames or [])
        if not (columns["a"] and columns["b"]):
            raise ImportFormatError(f"Could not find drug A/B columns. Headers are: {reader.fieldnames}")
        source_id = register_source(db, "DDInter", release, os.path.basename(path), digest,
                                    source_url, license_note)
        cache, rows = {}, 0
        for row in reader:
            ids = []
            for column in (columns["a"], columns["b"]):
                name = row[column].strip().lower()
                if name not in cache:
                    cache[name] = add_drug(db, name)
                ids.append(cache[name])
            record = "|".join(((row.get(columns["id_a"]) or "").strip() if columns["id_a"] else "",
                               (row.get(columns["id_b"]) or "").strip() if columns["id_b"] else "")).strip("|")
            add_interaction(db, ids[0], ids[1], row.get(columns["level"], "") if columns["level"] else "", "",
                            source_id, record or None)
            rows += 1
    missing = add_brand_aliases(db)
    db.commit()
    return ImportResult(rows=rows, drugs=len(cache), sha256=digest, missing_alias_targets=missing)
