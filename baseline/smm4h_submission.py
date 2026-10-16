#!/usr/bin/env python3
"""Create a BioCreative VII Task 3 CodaLab prediction archive.

Input is the unlabeled tab-separated test file with at least `tweet_id` and
`text` columns. The archive contains one `res/medlite_predictions.tsv` file
with the official evaluation-script columns. The official hidden test labels
are never read or created by this program.

  python3 smm4h_submission.py TEST.tsv medlite_submission.zip
  python3 smm4h_submission.py TEST.tsv medlite_fuzzy_submission.zip --fuzzy

Fuzzy mode emits top-1 candidates as predictions; it does not simulate user
confirmation. Choose its threshold using labeled training data only.
"""
import argparse
import csv
import io
import json
import zipfile
from pathlib import Path

import med
from recognition_baseline import build_alias_index, fuzzy_alias_index, recognize


SUBMISSION_COLUMNS = [
    "tweet_id", "user_id", "created_at", "text", "start", "end", "span", "drug"
]


def unique_tweets(input_path):
    tweets = {}
    with input_path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source, delimiter="\t")
        fields = set(reader.fieldnames or [])
        missing = {"tweet_id", "text"} - fields
        if missing:
            raise ValueError("input is missing required column(s): " + ", ".join(sorted(missing)))
        for line_number, row in enumerate(reader, start=2):
            tweet_id = (row.get("tweet_id") or "").strip()
            if not tweet_id:
                raise ValueError(f"line {line_number}: tweet_id is blank")
            text = row.get("text") or ""
            user_id = row.get("user_id") or ""
            created_at = row.get("created_at") or ""
            prior = tweets.get(tweet_id)
            if prior is not None:
                if prior["text"] != text:
                    raise ValueError(f"tweet_id {tweet_id} has conflicting text rows")
                continue
            tweets[tweet_id] = {
                "tweet_id": tweet_id,
                "user_id": user_id,
                "created_at": created_at,
                "text": text,
            }
    if not tweets:
        raise ValueError("input contains no tweets")
    return tweets


def make_submission(input_path, output_path, use_fuzzy=False, fuzzy_threshold=0.84):
    tweets = unique_tweets(input_path)
    db = med.connect()
    try:
        aliases = build_alias_index(db)
        fuzzy = fuzzy_alias_index(aliases) if use_fuzzy else None
        rows = []
        mention_count = 0
        for tweet in tweets.values():
            mentions = recognize(tweet["text"], aliases, fuzzy,
                                 fuzzy_threshold=fuzzy_threshold)
            if not mentions:
                rows.append([tweet[key] for key in ("tweet_id", "user_id", "created_at", "text")]
                            + ["-", "-", "-", "-"])
                continue
            for mention in mentions:
                start, end = int(mention["start"]), int(mention["end"])
                if tweet["text"][start:end] != mention["surface"]:
                    raise ValueError(f"recognizer returned an invalid span for tweet {tweet['tweet_id']}")
                rows.append([
                    tweet["tweet_id"], tweet["user_id"], tweet["created_at"], tweet["text"],
                    start, end, mention["surface"], mention["normalized"],
                ])
                mention_count += 1
    finally:
        db.close()

    text_buffer = io.StringIO(newline="")
    writer = csv.writer(text_buffer, delimiter="\t", lineterminator="\n")
    writer.writerow(SUBMISSION_COLUMNS)
    writer.writerows(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("res/medlite_predictions.tsv", text_buffer.getvalue())

    print(json.dumps({
        "submission_archive": str(output_path),
        "tweets": len(tweets),
        "predicted_mentions": mention_count,
        "method": "top-1 fuzzy candidates" if use_fuzzy else "exact dictionary",
        "fuzzy_threshold": fuzzy_threshold if use_fuzzy else None,
        "official_columns": SUBMISSION_COLUMNS,
        "scope": "prediction packaging only; no score computed because test gold labels are hidden",
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_tsv", type=Path,
                        help="official unlabeled TSV with tweet_id and text columns")
    parser.add_argument("output_zip", type=Path,
                        help="CodaLab archive to create")
    parser.add_argument("--fuzzy", action="store_true",
                        help="emit top-1 fuzzy candidates as predictions; not user-confirmed")
    parser.add_argument("--fuzzy-threshold", type=float, default=0.84,
                        help="minimum SequenceMatcher ratio for fuzzy mode; tune on training data only")
    args = parser.parse_args()
    if not 0 <= args.fuzzy_threshold <= 1:
        parser.error("--fuzzy-threshold must be between 0 and 1")
    make_submission(args.input_tsv, args.output_zip, args.fuzzy, args.fuzzy_threshold)


if __name__ == "__main__":
    main()
