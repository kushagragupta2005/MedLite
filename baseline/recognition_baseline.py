#!/usr/bin/env python3
"""Generate exact dictionary baseline predictions with mention spans."""
import argparse
import csv
import json
import math
import platform
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, for the medlite package

from medlite.recognition import FUZZY_THRESHOLD, AliasIndex, recognize as _recognize  # noqa: E402

import med  # noqa: E402  (opens the configured database: $MEDLITE_DB or baseline/med.db)


def recognize(text, index, top1_confirmed=False, fuzzy_threshold=FUZZY_THRESHOLD):
    """Benchmark-format mentions from the same matcher the app uses."""
    return [mention.as_benchmark_dict()
            for mention in _recognize(text, index, top1_fuzzy=top1_confirmed, threshold=fuzzy_threshold)]


def predict(corpus_path, output_path, split, top1_confirmed=False):
    db = med.connect()
    index = AliasIndex.from_db(db)
    with open(corpus_path, newline="", encoding="utf-8-sig") as source, \
            open(output_path, "w", newline="", encoding="utf-8") as target:
        reader = csv.DictReader(source)
        writer = csv.DictWriter(target, fieldnames=["example_id", "mentions_json"])
        writer.writeheader()
        count = 0
        for row in reader:
            if row["split"].strip().lower() != split:
                continue
            mentions = recognize(row["text"], index, top1_confirmed)
            writer.writerow({"example_id": row["example_id"],
                             "mentions_json": json.dumps(mentions, ensure_ascii=False)})
            count += 1
    db.close()
    method = "top-1 fuzzy suggestion with simulated user confirmation" if top1_confirmed else "exact dictionary"
    print(f"Wrote {count} {split} {method} predictions to {output_path}")


def measure_latency(corpus_path, split, repeats, top1_confirmed=False):
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    db = med.connect()
    index = AliasIndex.from_db(db)
    with open(corpus_path, newline="", encoding="utf-8-sig") as source:
        rows = [row for row in csv.DictReader(source)
                if row["split"].strip().lower() == split]
    db.close()
    if not rows:
        raise ValueError(f"no examples in split {split!r}")

    # Warm the matcher once per sentence; DB startup, index construction, and
    # file I/O are deliberately excluded from the per-sentence timings.
    for row in rows:
        recognize(row["text"], index, top1_confirmed)
    samples = []
    for _ in range(repeats):
        for row in rows:
            start = time.perf_counter_ns()
            recognize(row["text"], index, top1_confirmed)
            samples.append(time.perf_counter_ns() - start)
    samples.sort()
    p95 = samples[math.ceil(0.95 * len(samples)) - 1] / 1_000_000
    method = "top1_confirmed_candidate_generation" if top1_confirmed else "exact_dictionary"
    print(json.dumps({
        "method": method,
        "split": split,
        "draft_corpus": True,
        "examples": len(rows),
        "repeats_per_sentence": repeats,
        "measured_calls": len(samples),
        "warm_median_ms": statistics.median(samples) / 1_000_000,
        "warm_p95_ms": p95,
        "timed_scope": "tokenization, alias lookup, candidate generation; excludes database startup/index load and UI/user confirmation",
        "machine": platform.machine(),
        "macos": platform.mac_ver()[0] or None,
        "python": platform.python_version(),
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    predict_parser = sub.add_parser("predict", help="write span predictions")
    predict_parser.add_argument("corpus")
    predict_parser.add_argument("output")
    predict_parser.add_argument("--split", choices=("train", "validation", "test"), required=True)
    predict_parser.add_argument("--top1-confirmed", action="store_true",
                                help="simulate user confirmation of each top-1 suggestion; not automatic correction")
    latency_parser = sub.add_parser("latency", help="measure warm recognition time")
    latency_parser.add_argument("corpus")
    latency_parser.add_argument("--split", choices=("train", "validation", "test"), required=True)
    latency_parser.add_argument("--repeats", type=int, default=1000)
    latency_parser.add_argument("--top1-confirmed", action="store_true",
                                help="measure fuzzy candidate generation; user confirmation itself is not timed")
    args = parser.parse_args()
    if args.command == "predict":
        predict(args.corpus, args.output, args.split, args.top1_confirmed)
    else:
        measure_latency(args.corpus, args.split, args.repeats, args.top1_confirmed)


if __name__ == "__main__":
    main()
