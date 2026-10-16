#!/usr/bin/env python3
"""Read-only structural audit of the older SMM4H-2017 download.

Example:
  python3 data/audit_smm4h2017_download.py \
    ~/Downloads/rxwfb3tysd-2 \
    --output data/smm4h2017_download_audit.json

This script does not retrieve tweets, change source files, or repair annotations.
"""
import argparse
import collections
import hashlib
import json
import zipfile
from pathlib import Path


TASK_FILES = {
    "subtask1": ("training_set_1_ids.txt", "training_set_2_ids.txt", "evaluation_set_ids.txt"),
    "subtask2": ("training_set_1_ids.txt", "training_set_2_ids.txt", "evaluation_set_ids.txt"),
    "subtask3": (
        "task_3_normalization_training1.txt",
        "task_3_normalization_training2.txt",
        "task_3_normalization_training3.txt",
        "task_3_normalization_training4.txt",
        "task_3_normalization_evaluation.txt",
    ),
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_classification(path):
    rows = 0
    malformed = []
    ids = collections.Counter()
    labels = collections.Counter()
    with path.open(encoding="utf-8-sig") as source:
        for line_number, raw in enumerate(source, 1):
            if not raw.strip():
                continue
            fields = raw.rstrip("\r\n").split("\t")
            rows += 1
            if len(fields) != 3:
                malformed.append({"line": line_number, "field_count": len(fields)})
                continue
            ids[fields[0]] += 1
            labels[fields[-1]] += 1
    return {
        "rows": rows,
        "unique_ids": len(ids),
        "duplicate_id_rows": sum(count - 1 for count in ids.values() if count > 1),
        "label_counts": dict(sorted(labels.items())),
        "malformed_rows": malformed,
    }


def inspect_normalization(path):
    rows = 0
    field_counts = collections.Counter()
    malformed = []
    header_like = []
    with path.open(encoding="utf-8-sig") as source:
        for line_number, raw in enumerate(source, 1):
            if not raw.strip():
                continue
            fields = raw.rstrip("\r\n").split("\t")
            rows += 1
            field_counts[str(len(fields))] += 1
            if len(fields) != 3:
                malformed.append({"line": line_number, "field_count": len(fields), "fields": fields})
            if len(fields) == 3 and fields[0].lower() in {"id", "40000"} and "meddra" in " ".join(fields).lower():
                header_like.append({"line": line_number, "fields": fields})
    return {
        "rows": rows,
        "field_count_distribution": dict(sorted(field_counts.items())),
        "malformed_rows": malformed,
        "header_like_rows": header_like,
    }


def audit(root):
    tasks = {}
    for task, filenames in TASK_FILES.items():
        folder = root / task
        files = {}
        for filename in filenames:
            path = folder / filename
            if not path.is_file():
                files[filename] = {"error": "missing"}
            elif task in {"subtask1", "subtask2"}:
                files[filename] = inspect_classification(path)
            else:
                files[filename] = inspect_normalization(path)
        tasks[task] = files

    archives = {}
    for task in TASK_FILES:
        path = root / f"{task}.zip"
        if not path.is_file():
            archives[path.name] = {"error": "missing"}
            continue
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()
        archives[path.name] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "zip_integrity": "passed" if bad_member is None else "failed",
            "first_bad_member": bad_member,
        }

    return {
        "dataset": "SMM4H-2017 shared-task download",
        "source_directory": str(root),
        "read_only_audit": True,
        "scope": "structure and archive integrity only; no tweet retrieval or task-score computation",
        "tasks": tasks,
        "archives": archives,
        "decision": (
            "Do not use this download as the primary medication-name span benchmark. "
            "Subtasks 1 and 2 contain tweet IDs and labels, not tweet text; subtask 3 "
            "normalizes adverse-reaction phrases rather than medication mentions."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="extracted rxwfb3tysd-2 directory")
    parser.add_argument("--output", type=Path, help="optional JSON output path")
    args = parser.parse_args()
    result = audit(args.root.expanduser().resolve())
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
