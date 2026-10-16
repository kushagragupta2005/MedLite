#!/usr/bin/env python3
"""Audit local DDInter CSV files, hashes, pair deduplication, and DB counts."""
import argparse
import csv
import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path


EXPECTED_FILES = {
    f"ddinter_downloads_code_{letter}.csv"
    for letter in ("A", "B", "D", "H", "L", "P", "R", "V")
}
OFFICIAL_STATS = {
    "url": "https://ddinter.scbdd.com/statistics/",
    "reported_approved_entries": 1972,
    "reported_distinct_drugs": 1833,
    "reported_interaction_drug_pairs": 236834,
    "release": "DDInter 1.0; page reports last update 2020-09-04",
}


def normalized_header(value):
    return value.lower().replace(" ", "_")


def columns_for(headers):
    low = {column: normalized_header(column) for column in headers}
    drug_a = next((c for c in headers if re.fullmatch(r"drug(name)?_?(name_)?a", low[c])), None)
    drug_b = next((c for c in headers if re.fullmatch(r"drug(name)?_?(name_)?b", low[c])), None)
    severity = next((c for c in headers if "level" in low[c] or "sever" in low[c]), None)
    if not drug_a or not drug_b:
        raise ValueError(f"Could not identify drug A/B columns in headers: {headers}")
    return drug_a, drug_b, severity


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit(data_dir, database=None):
    data_dir = Path(data_dir)
    paths = sorted(data_dir.glob("ddinter_downloads_code_*.csv"))
    if not paths:
        raise ValueError(f"No DDInter CSV files found in {data_dir}")
    observed_names = {path.name for path in paths}
    global_pairs = defaultdict(list)
    all_drugs, files = set(), []
    total_rows = 0
    for path in paths:
        pair_count, drugs, rows = set(), set(), 0
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            drug_a, drug_b, severity_col = columns_for(reader.fieldnames or [])
            for row in reader:
                a = (row.get(drug_a) or "").strip().lower()
                b = (row.get(drug_b) or "").strip().lower()
                if not a or not b:
                    continue
                pair = tuple(sorted((a, b)))
                severity = (row.get(severity_col) or "").strip().lower() if severity_col else ""
                global_pairs[pair].append((severity, path.name))
                pair_count.add(pair)
                drugs.update((a, b))
                rows += 1
        total_rows += rows
        all_drugs.update(drugs)
        files.append({"filename": path.name, "bytes": path.stat().st_size,
                      "sha256": sha256(path), "input_rows": rows,
                      "unique_unordered_pairs": len(pair_count),
                      "unique_drug_names": len(drugs)})
    duplicate_pairs = [records for records in global_pairs.values() if len(records) > 1]
    multi_file_pairs = [records for records in duplicate_pairs
                        if len({filename for _, filename in records}) > 1]
    severity_conflicts = [records for records in duplicate_pairs
                          if len({severity for severity, _ in records}) > 1]
    result = {
        "source": "DDInter local CSV export",
        "files": files,
        "file_set_check": {
            "matches_current_download_page_names": observed_names == EXPECTED_FILES,
            "missing_expected": sorted(EXPECTED_FILES - observed_names),
            "unexpected_local": sorted(observed_names - EXPECTED_FILES),
            "expected_files_source": "https://ddinter.scbdd.com/download/",
        },
        "local_data": {
            "input_rows": total_rows,
            "unique_drug_names": len(all_drugs),
            "unique_unordered_pairs": len(global_pairs),
            "duplicate_rows_after_unordered_pair_dedup": total_rows - len(global_pairs),
            "pairs_repeated_in_source_rows": len(duplicate_pairs),
            "pairs_present_in_multiple_files": len(multi_file_pairs),
            "duplicate_pairs_with_severity_conflicts": len(severity_conflicts),
        },
        "official_statistics_as_reported": OFFICIAL_STATS,
        "interpretation": "Local counts use drug-name pairs deduplicated as unordered pairs; official statistics use DDInter's published terminology. Do not assume the counts are directly comparable or claim completeness until reconciled.",
    }
    if database:
        uri = Path(database).resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as db:
            result["imported_database"] = {
                "path": str(Path(database)),
                "drug_names": db.execute("SELECT COUNT(*) FROM drug").fetchone()[0],
                "aliases": db.execute("SELECT COUNT(*) FROM alias").fetchone()[0],
                "unique_interactions": db.execute("SELECT COUNT(*) FROM interaction").fetchone()[0],
                "unattributed_interactions": db.execute("SELECT COUNT(*) FROM interaction WHERE source_id IS NULL").fetchone()[0],
                "data_source_records": db.execute("SELECT COUNT(*) FROM data_source WHERE name='DDInter'").fetchone()[0],
            }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="../data")
    parser.add_argument("--database", default="med.db")
    parser.add_argument("--output", default="../data/ddinter_audit.json")
    args = parser.parse_args()
    result = audit(args.data_dir, args.database)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote audit to {output}")
    print(json.dumps(result["local_data"], indent=2))
    print("file set matches download page:", result["file_set_check"]["matches_current_download_page_names"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
