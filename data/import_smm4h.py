#!/usr/bin/env python3
"""Convert an official labeled SMM4H TSV into MedLite's mention-corpus CSV.

Use only on the labeled training or validation file obtained through the
official access route. Test inputs are unlabeled and must be sent to CodaLab,
not converted to a fabricated gold corpus.

  python3 data/import_smm4h.py TRAIN.tsv data/smm4h_train.csv --split train
  python3 data/import_smm4h.py VALIDATION.tsv data/smm4h_validation.csv --split validation
"""
import argparse
import csv
import json
import re
from collections import Counter, OrderedDict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
OUTPUT_COLUMNS = [
    "example_id", "source_group", "split", "text", "mentions_json", "category",
    "provenance", "license_or_permission", "review_status",
]
PROVENANCE = "BioCreative VII Task 3 / SMM4HDrug labeled release"
ACCESS_NOTE = (
    "Obtained through official shared-task access; retain locally and follow the "
    "current source terms; do not redistribute tweet text"
)


def signature(text):
    return tuple(token.group(0).lower() for token in TOKEN.finditer(text))


def canonical_name(official_name, aliases):
    match = aliases.get(signature(official_name))
    if match:
        return match[1], True
    # Explicit sentinel ensures an unmapped gold name is a strict-task false
    # negative instead of being dropped or accidentally treated as a match.
    return "__OOV__:" + (official_name or "<blank>"), False


def load_alias_index():
    import sys
    sys.path.insert(0, str(ROOT / "baseline"))
    import med
    from recognition_baseline import build_alias_index

    db = med.connect()
    try:
        return build_alias_index(db)
    finally:
        db.close()


def convert(source_path, output_path, split, summary_path):
    aliases = load_alias_index()
    examples = OrderedDict()
    oov_names = Counter()
    annotated_mentions = 0
    mapped_mentions = 0

    with source_path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source, delimiter="\t")
        required = {"tweet_id", "text", "start", "end", "span", "drug"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError("labeled source is missing required column(s): "
                             + ", ".join(sorted(missing)))
        for line_number, row in enumerate(reader, start=2):
            tweet_id = (row.get("tweet_id") or "").strip()
            text = row.get("text") or ""
            if not tweet_id:
                raise ValueError(f"line {line_number}: tweet_id is blank")
            key = "smm4h-" + tweet_id
            if key not in examples:
                examples[key] = {"text": text, "mentions": []}
            elif examples[key]["text"] != text:
                raise ValueError(f"tweet_id {tweet_id} has conflicting text rows")

            surface = row.get("span") or ""
            if not surface or surface == "-":
                continue
            try:
                start, end = int(row["start"]), int(row["end"])
            except (TypeError, ValueError):
                raise ValueError(f"line {line_number}: mention span has invalid offsets")
            if start < 0 or end <= start or text[start:end] != surface:
                raise ValueError(
                    f"line {line_number}: source span [{start}, {end}) does not match text"
                )
            official_name = (row.get("drug") or "").strip()
            normalized, mapped = canonical_name(official_name, aliases)
            annotated_mentions += 1
            mapped_mentions += bool(mapped)
            if not mapped:
                oov_names[official_name or "<blank>"] += 1
            mention = {
                "start": start,
                "end": end,
                "surface": surface,
                "normalized": normalized,
            }
            if mention not in examples[key]["mentions"]:
                examples[key]["mentions"].append(mention)

    if not examples:
        raise ValueError("source file contains no tweet rows")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for example_id, example in examples.items():
            mentions = sorted(example["mentions"], key=lambda item: (item["start"], item["end"]))
            writer.writerow({
                "example_id": example_id,
                # Tweet IDs are unique row groups. Official splits are retained;
                # shared users can occur across splits by benchmark design.
                "source_group": example_id,
                "split": split,
                "text": example["text"],
                "mentions_json": json.dumps(mentions, ensure_ascii=False),
                "category": "mention" if mentions else "no_medicine",
                "provenance": PROVENANCE,
                "license_or_permission": ACCESS_NOTE,
                "review_status": "approved",
            })

    summary = {
        "dataset": "SMM4HDrug / BioCreative VII Task 3",
        "source_file": source_path.name,
        "converted_file": output_path.name,
        "split": split,
        "tweets": len(examples),
        "annotated_mentions": annotated_mentions,
        "duplicate_spans_removed": annotated_mentions - sum(
            len(item["mentions"]) for item in examples.values()),
        "mentions_mapped_to_medlite_inventory": mapped_mentions,
        "mentions_unmapped_to_medlite_inventory": annotated_mentions - mapped_mentions,
        "unmapped_official_names": dict(oov_names.most_common()),
        "note": (
            "Normalization uses exact tokenized matching against the current MedLite alias "
            "inventory. Unmapped gold names are retained with __OOV__ sentinels and count "
            "against strict normalized-name recall. Official benchmark scoring is span-only."
        ),
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_tsv", type=Path,
                        help="official labeled TSV; do not use unlabeled test input")
    parser.add_argument("output_csv", type=Path, help="MedLite-format labeled CSV")
    parser.add_argument("--split", choices=("train", "validation"), required=True)
    parser.add_argument("--summary", type=Path,
                        help="summary JSON path (default: <output stem>_summary.json)")
    args = parser.parse_args()
    summary_path = args.summary or args.output_csv.with_name(args.output_csv.stem + "_summary.json")
    convert(args.source_tsv, args.output_csv, args.split, summary_path)


if __name__ == "__main__":
    main()
