#!/usr/bin/env python3
"""Audit local MedMentions ST21pv corpus structure and lexicon overlap.

This produces corpus counts and exact token-signature overlap only. It does not
compute drug-recognition precision/recall: T103 covers chemical concepts, not
only medicines, and textual overlap does not establish drug identity.

Run from the project root:
  python3 data/audit_medmentions.py
"""
import argparse
import collections
import gzip
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
SPLITS = ("train", "dev", "test")
SPLIT_SOURCE_NAMES = {"train": "trng", "dev": "dev", "test": "test"}
CORPUS_URL = (
    "https://raw.githubusercontent.com/chanzuckerberg/MedMentions/"
    "master/st21pv/data/corpus_pubtator.txt.gz"
)
SPLIT_URL_BASE = (
    "https://raw.githubusercontent.com/chanzuckerberg/MedMentions/"
    "master/full/data/corpus_pubtator_pmids_"
)


def token_signature(text):
    return tuple(match.group(0).lower() for match in TOKEN.finditer(text))


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_splits(directory):
    splits = {}
    for split in SPLITS:
        path = directory / f"medmentions_{split}_pmids.txt"
        if not path.exists():
            raise FileNotFoundError(f"missing official split list: {path}")
        ids = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
               if line.strip()]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate PMID in split list: {path}")
        splits[split] = set(ids)
    for index, left in enumerate(SPLITS):
        for right in SPLITS[index + 1:]:
            overlap = splits[left] & splits[right]
            if overlap:
                raise ValueError(f"official split lists overlap: {left}/{right} ({len(overlap)})")
    return splits


def load_alias_signatures():
    sys.path.insert(0, str(ROOT / "baseline"))
    import med

    db = med.connect()
    try:
        return {token_signature(row[0])
                for row in db.execute("SELECT alias FROM alias")
                if token_signature(row[0])}
    finally:
        db.close()


def audit(corpus, split_dir):
    split_ids = load_splits(split_dir)
    split_paths = {name: split_dir / f"medmentions_{name}_pmids.txt" for name in SPLITS}
    alias_signatures = load_alias_signatures()
    totals = collections.Counter()
    split_counts = collections.defaultdict(collections.Counter)
    docs_seen = set()
    offset_mismatches = 0
    current_pmid = None
    title = abstract = ""

    with gzip.open(corpus, "rt", encoding="utf-8") as source:
        for raw_line in source:
            line = raw_line.rstrip("\r\n")
            if not line:
                continue
            if "\t" not in line:
                fields = line.split("|", 2)
                if len(fields) != 3:
                    totals["malformed_document_lines"] += 1
                    continue
                pmid, kind, text = fields
                if kind == "t":
                    current_pmid, title, abstract = pmid, text, ""
                elif kind == "a":
                    if pmid != current_pmid:
                        totals["orphan_abstract_lines"] += 1
                    abstract = text
                    if pmid not in docs_seen:
                        docs_seen.add(pmid)
                        totals["documents_with_abstract"] += 1
                        split = next((name for name, ids in split_ids.items()
                                      if pmid in ids), "unassigned")
                        split_counts[split]["documents"] += 1
                continue

            fields = line.split("\t")
            if len(fields) < 6:
                totals["malformed_annotation_rows"] += 1
                continue
            pmid, start, end, surface, semantic_types, cui = fields[:6]
            totals["annotation_rows"] += 1
            split = next((name for name, ids in split_ids.items()
                          if pmid in ids), "unassigned")
            split_counts[split]["annotation_rows"] += 1
            if "T103" not in semantic_types.split(","):
                continue

            totals["T103_chemical_mentions"] += 1
            split_counts[split]["T103_chemical_mentions"] += 1
            full_text = title + " " + abstract
            try:
                valid_offset = full_text[int(start):int(end)] == surface
            except (ValueError, TypeError):
                valid_offset = False
            if not valid_offset:
                offset_mismatches += 1

            signature = token_signature(surface)
            if signature and signature in alias_signatures:
                totals["T103_mentions_matching_medlite_alias_tokens"] += 1
                split_counts[split]["T103_alias_token_matches"] += 1

    missing_pmids = set().union(*split_ids.values()) - docs_seen
    extra_pmids = docs_seen - set().union(*split_ids.values())
    chemical_count = totals["T103_chemical_mentions"]
    return {
        "dataset": "MedMentions ST21pv",
        "audit_date": date.today().isoformat(),
        "corpus_file": corpus.name,
        "corpus_url": CORPUS_URL,
        "corpus_sha256": sha256(corpus),
        "split_files": {
            split: {
                "file": f"medmentions_{split}_pmids.txt",
                "url": SPLIT_URL_BASE + SPLIT_SOURCE_NAMES[split] + ".txt",
                "documents_in_list": len(ids),
                "sha256": sha256(split_paths[split]),
            }
            for split, ids in split_ids.items()
        },
        "corpus_document_count": totals["documents_with_abstract"],
        "annotation_rows": totals["annotation_rows"],
        "T103_chemical_mentions": chemical_count,
        "T103_mentions_matching_medlite_alias_tokens": totals[
            "T103_mentions_matching_medlite_alias_tokens"],
        "T103_alias_token_overlap_fraction": (
            totals["T103_mentions_matching_medlite_alias_tokens"] / chemical_count
            if chemical_count else None
        ),
        "offset_mismatches_among_T103": offset_mismatches,
        "split_list_pmids_missing_from_corpus": len(missing_pmids),
        "corpus_pmids_missing_from_split_lists": len(extra_pmids),
        "split_counts": {name: dict(split_counts[name]) for name in (*SPLITS, "unassigned")
                         if split_counts[name]},
        "interpretation": (
            "Counts and alias-token overlap are corpus diagnostics only. T103 includes "
            "chemicals beyond medicines; lexical overlap is not a drug identity mapping "
            "and must not be reported as drug-recognition F1."
        ),
        "license_note": (
            "The MedMentions maintainers release the corpus under CC0. Source abstracts "
            "originate from PubMed; keep source attribution and corpus terms with any reuse."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path,
                        default=ROOT / "data/medmentions_st21pv_corpus_pubtator.txt.gz")
    parser.add_argument("--split-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output", type=Path, default=ROOT / "data/medmentions_audit.json")
    args = parser.parse_args()
    report = audit(args.corpus, args.split_dir)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
