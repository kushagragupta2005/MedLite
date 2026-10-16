#!/usr/bin/env python3
"""Generate exact dictionary baseline predictions with mention spans."""
import argparse
import csv
import difflib
import json
import math
import platform
import re
import statistics
import time

import med


TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def build_alias_index(db):
    index = {}
    for alias, drug_id in db.execute("SELECT alias, drug_id FROM alias"):
        parts = tuple(token.group(0).lower() for token in TOKEN.finditer(alias))
        if parts:
            index[parts] = (drug_id, med.drug_name(db, drug_id))
    return index


def fuzzy_alias_index(alias_index):
    candidates = {}
    for alias, value in alias_index.items():
        if len(alias) == 1 and len(alias[0]) >= 5 and alias[0].isalpha():
            key = (alias[0][0], len(alias[0]))
            candidates.setdefault(key, []).append((alias[0], value))
    return candidates


def recognize(text, alias_index, fuzzy_index=None, fuzzy_threshold=0.84):
    tokens = list(TOKEN.finditer(text))
    words = [token.group(0).lower() for token in tokens]
    max_length = max((len(alias) for alias in alias_index), default=0)
    mentions, index = [], 0
    while index < len(tokens):
        match = None
        for length in range(min(max_length, len(tokens) - index), 0, -1):
            entry = alias_index.get(tuple(words[index:index + length]))
            if entry:
                match = (length, entry)
                break
        if not match and fuzzy_index and words[index].isalpha() and len(words[index]) >= 6:
            word = words[index]
            candidates = []
            for candidate_length in range(max(5, len(word) - 2), len(word) + 3):
                for alias, value in fuzzy_index.get((word[0], candidate_length), ()):
                    ratio = difflib.SequenceMatcher(None, word, alias).ratio()
                    if ratio >= fuzzy_threshold:
                        candidates.append((ratio, value[1], alias, value))
            if candidates:
                candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
                match = (1, candidates[0][3])
        if not match:
            index += 1
            continue
        length, (_, normalized) = match
        start, end = tokens[index].start(), tokens[index + length - 1].end()
        mentions.append({"start": start, "end": end,
                         "surface": text[start:end], "normalized": normalized})
        index += length
    return mentions


def predict(corpus_path, output_path, split, top1_confirmed=False):
    db = med.connect()
    aliases = build_alias_index(db)
    fuzzy = fuzzy_alias_index(aliases) if top1_confirmed else None
    with open(corpus_path, newline="", encoding="utf-8-sig") as source, \
            open(output_path, "w", newline="", encoding="utf-8") as target:
        reader = csv.DictReader(source)
        writer = csv.DictWriter(target, fieldnames=["example_id", "mentions_json"])
        writer.writeheader()
        count = 0
        for row in reader:
            if row["split"].strip().lower() != split:
                continue
            mentions = recognize(row["text"], aliases, fuzzy)
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
    aliases = build_alias_index(db)
    fuzzy = fuzzy_alias_index(aliases) if top1_confirmed else None
    with open(corpus_path, newline="", encoding="utf-8-sig") as source:
        rows = [row for row in csv.DictReader(source)
                if row["split"].strip().lower() == split]
    db.close()
    if not rows:
        raise ValueError(f"no examples in split {split!r}")

    # Warm the matcher once per sentence; DB startup, index construction, and
    # file I/O are deliberately excluded from the per-sentence timings.
    for row in rows:
        recognize(row["text"], aliases, fuzzy)
    samples = []
    for _ in range(repeats):
        for row in rows:
            start = time.perf_counter_ns()
            recognize(row["text"], aliases, fuzzy)
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
