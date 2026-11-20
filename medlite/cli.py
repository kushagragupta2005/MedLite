"""Command-line interface: ``python3 -m medlite <command>`` (or ``python3 baseline/med.py <command>``)."""
import argparse
import os
import sys
import time

from .answer import answer
from .config import Settings
from .db import SEV_ORDER_SQL, connect, drug_count
from .demo import load_demo
from .ingest import ImportFormatError, load_ddinter_csv
from .lookup import lookup
from .recognition import AliasIndex, find_drugs

EMPTY_DB_HINT = "The database has no medicines yet. Run `init` for demo data or `load` for a DDInter CSV."


def cmd_init(settings, args):
    db = connect(settings.db_path)
    load_demo(db)
    db.close()
    print("Created", settings.db_path, "with DEMO data. Use `load` for the real DDInter data.")


def cmd_load(settings, args):
    db = connect(settings.db_path)
    try:
        result = load_ddinter_csv(db, args.csv, release=args.release)
    except ImportFormatError as error:
        sys.exit(str(error))
    finally:
        db.close()
    if result.missing_alias_targets:
        print("Note: not found in this data (alias skipped):", ", ".join(result.missing_alias_targets))
    print(f"Imported {result.rows} rows ({result.drugs} drugs) from {os.path.basename(args.csv)}.")
    print(f"Source: DDInter {args.release}; SHA-256 {result.sha256}")


def cmd_ask(settings, args):
    response = answer(" ".join(args.question), settings=settings)
    if response.get("corrections"):
        print("Confirmed spelling: " + ", ".join(response["corrections"]))
    found = response["found"]
    print(("Recognised: " + ", ".join(found) + "\n" if found else "") + response["facts"])
    for suggestion in response.get("suggestions", []):
        options = ", ".join(option["name"] for option in suggestion["options"])
        print(f"\nPossible match for {suggestion['input']!r}: {options}. Re-run with the intended spelling to check it.")
    if response.get("summary"):
        print("\nSummary (AI):", response["summary"])
    elif response.get("summary_withheld"):
        print("\nSummary (AI) not shown:", response["summary_withheld"])
    print("\n" + response["disclaimer"])


def cmd_stats(settings, args):
    db = connect(settings.db_path)
    drugs = drug_count(db)
    aliases = db.execute("SELECT COUNT(*) FROM alias").fetchone()[0]
    interactions = db.execute("SELECT COUNT(*) FROM interaction").fetchone()[0]
    print(f"drugs: {drugs}   aliases: {aliases}   interactions: {interactions}")
    print("recorded source files:", db.execute("SELECT COUNT(*) FROM data_source").fetchone()[0])
    unattributed = db.execute("SELECT COUNT(*) FROM interaction WHERE source_id IS NULL").fetchone()[0]
    print("interactions without import provenance:", unattributed)
    for name, release, source_file, digest in db.execute(
            "SELECT name, release, source_file, sha256 FROM data_source ORDER BY name, release, source_file"):
        print(f"  source: {name} {release} / {source_file} / sha256:{digest[:12]}")
    for severity, count in db.execute(
            f"SELECT severity, COUNT(*) FROM interaction GROUP BY severity ORDER BY {SEV_ORDER_SQL}"):
        print(f"  {severity:9s} {count:7d}  ({100 * count / max(interactions, 1):.1f}%)")
    if os.path.exists(settings.db_path):
        print(f"db file size: {os.path.getsize(settings.db_path) / 1e6:.1f} MB")
    ids = find_drugs("warfarin acetaminophen ibuprofen aspirin", AliasIndex.from_db(db), fuzzy=False).drug_ids
    if len(ids) > 1:
        start = time.perf_counter()
        for _ in range(200):
            lookup(db, ids)
        print(f"pair lookup ({len(ids)} drugs): {(time.perf_counter() - start) / 200 * 1000:.2f} ms avg")
    print("index plan:", db.execute("EXPLAIN QUERY PLAN SELECT * FROM interaction WHERE a=? OR b=?", (1, 1)).fetchall())
    db.close()


def cmd_serve(settings, args):
    from .server import make_server
    db = connect(settings.db_path)
    empty = drug_count(db) == 0
    db.close()
    if empty:
        print(EMPTY_DB_HINT)
    server = make_server(settings, port=args.port)
    print(f"Open http://127.0.0.1:{server.server_port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def build_parser():
    parser = argparse.ArgumentParser(prog="medlite", description="Offline drug-interaction lookup. "
                                     "Information tool only - not medical advice.")
    parser.add_argument("--db", help="database path (default: $MEDLITE_DB or baseline/med.db)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create the database with small DEMO data").set_defaults(func=cmd_init)
    load = sub.add_parser("load", help="import a DDInter CSV (real data)")
    load.add_argument("csv")
    load.add_argument("--release", default="unspecified",
                      help="label describing your downloaded snapshot, e.g. local-export-2026-10-11")
    load.set_defaults(func=cmd_load)
    ask = sub.add_parser("ask", help='ask a question, e.g. ask "warfarin and ibuprofen?"')
    ask.add_argument("question", nargs="+")
    ask.set_defaults(func=cmd_ask)
    sub.add_parser("stats", help="database numbers for reports").set_defaults(func=cmd_stats)
    serve = sub.add_parser("serve", help="web UI on http://127.0.0.1:PORT")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=cmd_serve)
    for command in (ask, serve):
        command.add_argument("--llm", action="store_true", help="add a guarded plain-language summary via Ollama")
        command.add_argument("--exact", action="store_true", help="disable spelling suggestions")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    settings = Settings.from_env(
        db_path=args.db,
        use_llm=getattr(args, "llm", False) or None,
        fuzzy=False if getattr(args, "exact", False) else None,
    )
    args.func(settings, args)


if __name__ == "__main__":
    main()
