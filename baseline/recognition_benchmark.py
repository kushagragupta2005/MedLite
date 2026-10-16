#!/usr/bin/env python3
"""Validate a MedLite mention corpus and score span-level predictions.

Standard library only. Offsets are Python string offsets: start inclusive,
end exclusive. A true positive requires an exact span and normalized name.

  python3 recognition_benchmark.py validate ../data/recognition_gold_template.csv
  python3 recognition_benchmark.py score GOLD.csv PREDICTIONS.csv

Prediction CSV columns: example_id,mentions_json. The JSON mention objects
use the same start/end/surface/normalized format as the gold template.
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict


REQUIRED_COLUMNS = {
    "example_id", "source_group", "split", "text", "mentions_json",
    "category", "provenance", "license_or_permission", "review_status",
}
SPLITS = {"train", "validation", "test"}


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - fields
        if missing:
            raise ValueError(f"{path}: missing columns: {', '.join(sorted(missing))}")
        return list(reader)


def read_mentions(raw, text, row_id, issues):
    try:
        mentions = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        issues.append(f"{row_id}: invalid mentions_json ({exc.msg})")
        return []
    if not isinstance(mentions, list):
        issues.append(f"{row_id}: mentions_json must be a list")
        return []
    valid = []
    for index, mention in enumerate(mentions):
        label = f"{row_id}: mention {index + 1}"
        if not isinstance(mention, dict):
            issues.append(f"{label} must be an object")
            continue
        try:
            start, end = int(mention["start"]), int(mention["end"])
            surface, normalized = mention["surface"], mention["normalized"]
            if not isinstance(surface, str) or not isinstance(normalized, str):
                raise TypeError
        except (KeyError, TypeError, ValueError):
            issues.append(f"{label} needs integer start/end and string surface/normalized")
            continue
        if start < 0 or end <= start or end > len(text):
            issues.append(f"{label} has an invalid span [{start}, {end})")
            continue
        if text[start:end] != surface:
            issues.append(f"{label} surface does not match text[{start}:{end}]")
            continue
        if not normalized.strip():
            issues.append(f"{label} has an empty normalized name")
            continue
        valid.append((start, end, surface, normalized))
    return valid


def validate(rows, strict=True):
    issues, seen_ids, group_splits = [], set(), defaultdict(set)
    if not rows:
        issues.append("corpus has no annotation rows")
    for number, row in enumerate(rows, start=2):
        rid = row.get("example_id", "").strip() or f"row {number}"
        if rid in seen_ids:
            issues.append(f"{rid}: duplicate example_id")
        seen_ids.add(rid)
        group = row.get("source_group", "").strip()
        split = row.get("split", "").strip().lower()
        if not group:
            issues.append(f"{rid}: source_group is required")
        elif split:
            group_splits[group].add(split)
        if split not in SPLITS:
            issues.append(f"{rid}: split must be one of {', '.join(sorted(SPLITS))}")
        if not row.get("category", "").strip():
            issues.append(f"{rid}: category is required")
        if strict:
            if row.get("review_status", "").strip().lower() != "approved":
                issues.append(f"{rid}: review_status must be approved")
            if not row.get("provenance", "").strip():
                issues.append(f"{rid}: provenance is required")
            if not row.get("license_or_permission", "").strip():
                issues.append(f"{rid}: license_or_permission is required")
        read_mentions(row.get("mentions_json", ""), row.get("text", ""), rid, issues)
    for group, splits in group_splits.items():
        if len(splits) > 1:
            issues.append(f"source_group {group!r} crosses splits: {', '.join(sorted(splits))}")
    return issues


def prediction_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        needed = {"example_id", "mentions_json"}
        missing = needed - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing columns: {', '.join(sorted(missing))}")
        out = {}
        for row in reader:
            rid = row["example_id"].strip()
            if not rid or rid in out:
                raise ValueError(f"{path}: blank or duplicate example_id {rid!r}")
            out[rid] = row.get("mentions_json", "[]")
        return out


def counts_for(mentions):
    return Counter((start, end, normalized) for start, end, _, normalized in mentions)


def prf(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision is not None and recall is not None and precision + recall else None)
    return {"precision": precision, "recall": recall, "f1": f1,
            "tp": tp, "fp": fp, "fn": fn}


def score(gold_path, pred_path, split="test", allow_draft=False):
    rows = read_csv(gold_path)
    if allow_draft and split == "test":
        raise ValueError("draft test scoring is disabled; approve and lock the test corpus first")
    issues = validate(rows, strict=not allow_draft)
    if issues:
        raise ValueError("Gold corpus validation failed:\n" + "\n".join(issues[:30]))
    rows = [row for row in rows if row["split"].strip().lower() == split]
    if not rows:
        raise ValueError(f"Gold corpus has no rows in the {split!r} split")
    predictions = prediction_rows(pred_path)
    gold_ids = {row["example_id"].strip() for row in rows}
    extra = set(predictions) - gold_ids
    if extra:
        raise ValueError("Predictions contain unknown example_id(s): " + ", ".join(sorted(extra)[:10]))
    missing = gold_ids - set(predictions)
    if missing:
        raise ValueError("Predictions are missing example_id(s): " + ", ".join(sorted(missing)[:10]))
    totals = Counter()
    categories = defaultdict(Counter)
    exact_sentences = 0
    for row in rows:
        rid = row["example_id"].strip()
        text = row["text"]
        gold_issues, pred_issues = [], []
        gold = counts_for(read_mentions(row["mentions_json"], text, rid, gold_issues))
        raw_pred = predictions.get(rid, "[]")
        pred = counts_for(read_mentions(raw_pred, text, rid, pred_issues))
        if pred_issues:
            raise ValueError("Invalid prediction(s):\n" + "\n".join(pred_issues[:30]))
        tp = sum((gold & pred).values())
        fp, fn = sum((pred - gold).values()), sum((gold - pred).values())
        totals.update({"tp": tp, "fp": fp, "fn": fn})
        categories[row["category"].strip()].update({"tp": tp, "fp": fp, "fn": fn})
        exact_sentences += (gold == pred)
    result = {"split": split, "examples": len(rows),
              "corpus_status": "DRAFT: synthetic/unreviewed; diagnostic only" if allow_draft else "approved",
              "exact_sentence_match": exact_sentences / len(rows),
              "micro": prf(totals["tp"], totals["fp"], totals["fn"]),
              "by_category": {name: prf(c["tp"], c["fp"], c["fn"])
                              for name, c in sorted(categories.items())}}
    print(json.dumps(result, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate_parser = sub.add_parser("validate", help="check annotations, provenance, and group splits")
    validate_parser.add_argument("corpus")
    validate_parser.add_argument("--allow-draft", action="store_true",
                                 help="allow unapproved rows and missing provenance/license fields")
    score_parser = sub.add_parser("score", help="score exact-span predictions against an approved corpus")
    score_parser.add_argument("gold")
    score_parser.add_argument("predictions")
    score_parser.add_argument("--split", choices=sorted(SPLITS), default="test",
                              help="scoring split (default: test)")
    score_parser.add_argument("--allow-draft", action="store_true",
                              help="allow draft data for train/validation diagnostics; never permits draft test scoring")
    args = parser.parse_args()
    try:
        if args.command == "validate":
            rows = read_csv(args.corpus)
            issues = validate(rows, strict=not args.allow_draft)
            print(f"rows: {len(rows)}")
            if issues:
                print("Validation issues:")
                for issue in issues:
                    print("-", issue)
                return 1
            print("Corpus structure and source-group splits are valid.")
            return 0
        score(args.gold, args.predictions, args.split, args.allow_draft)
        return 0
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
