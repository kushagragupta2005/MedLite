#!/usr/bin/env python3
"""Create two blinded annotation sheets without gold labels or split names."""
import argparse
import csv
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", nargs="?")
    parser.add_argument("--out-dir")
    args = parser.parse_args()
    corpus = Path(args.corpus) if args.corpus else ROOT / "recognition_seed_draft.csv"
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "review_packets"
    out_dir.mkdir(parents=True, exist_ok=True)
    with corpus.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    if not rows or not {"example_id", "text"}.issubset(reader.fieldnames or []):
        raise SystemExit("Corpus must contain example_id and text columns and at least one row")
    rows = sorted(rows, key=lambda row: row["example_id"])
    key_rows = []
    for index, row in enumerate(rows, start=1):
        key_rows.append({"blind_id": f"item-{index:04d}", "example_id": row["example_id"]})
    with (out_dir / "coordinator_key.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["blind_id", "example_id"])
        writer.writeheader()
        writer.writerows(key_rows)
    for reviewer, seed in (("reviewer_a.csv", 9137), ("reviewer_b.csv", 4619)):
        packet = [{"blind_id": key["blind_id"], "text": row["text"],
                   "mentions_json": "", "decision": "", "notes": ""}
                  for key, row in zip(key_rows, rows)]
        random.Random(seed).shuffle(packet)
        with (out_dir / reviewer).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["blind_id", "text", "mentions_json", "decision", "notes"])
            writer.writeheader()
            writer.writerows(packet)
    print(f"Prepared blinded packets for {len(rows)} examples in {out_dir}")
    print("Keep coordinator_key.csv away from annotators until both packets are complete.")


if __name__ == "__main__":
    main()
