#!/usr/bin/env python3
"""MedLite - tiny offline drug-interaction assistant.

Stdlib only. The DATABASE is the source of truth; an optional tiny local
model (via Ollama) only rewrites the database result in plain language.

  python3 med.py init                 create med.db with small DEMO data
  python3 med.py load ddinter.csv     import a DDInter CSV (real data)
  python3 med.py ask "warfarin and ibuprofen?"  [--llm]
  python3 med.py stats                numbers for your report
  python3 med.py serve [--llm]        web UI at http://127.0.0.1:8000

Information tool only - not medical advice.
"""
import csv, difflib, hashlib, itertools, json, os, re, sqlite3, sys, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

DB = os.environ.get("MEDLITE_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "med.db"))
MODEL = "qwen2.5:0.5b"          # ~400 MB; any Ollama model name works
USE_LLM = "--llm" in sys.argv
FUZZY = "--exact" not in sys.argv   # spelling tolerance (off with --exact)
LOG_QUERIES = os.environ.get("MEDLITE_LOG_QUERIES", "").lower() in ("1", "true", "yes")
SEV_ORDER = "CASE severity WHEN 'major' THEN 0 WHEN 'moderate' THEN 1 WHEN 'minor' THEN 2 ELSE 3 END"
DISCLAIMER = ("Information only; not medical advice or a diagnosis. A database miss does not establish safety. "
              "Ask a doctor or pharmacist.")

SCHEMA = """
CREATE TABLE IF NOT EXISTS drug(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS alias(alias TEXT PRIMARY KEY, drug_id INTEGER NOT NULL REFERENCES drug(id));
CREATE TABLE IF NOT EXISTS data_source(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, release TEXT NOT NULL,
  imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, source_file TEXT NOT NULL,
  sha256 TEXT NOT NULL, source_url TEXT, license_note TEXT,
  UNIQUE(name, release, source_file, sha256));
CREATE TABLE IF NOT EXISTS interaction(
  a INTEGER NOT NULL REFERENCES drug(id), b INTEGER NOT NULL REFERENCES drug(id),
  severity TEXT NOT NULL CHECK(severity IN ('major','moderate','minor','unknown')),
  note TEXT, source_id INTEGER REFERENCES data_source(id), source_record_id TEXT,
  PRIMARY KEY(a, b), CHECK(a < b));
CREATE INDEX IF NOT EXISTS ix_interaction_b ON interaction(b);
CREATE TABLE IF NOT EXISTS log(id INTEGER PRIMARY KEY, ts TEXT DEFAULT CURRENT_TIMESTAMP,
  question TEXT, found TEXT, answer TEXT);
"""

# DEMO data: small, well-known interactions. Replace with DDInter via `load`.
DEMO_DRUGS = {
    "warfarin": ["coumadin"], "ibuprofen": ["brufen", "advil", "motrin"],
    "aspirin": ["ecosprin", "disprin"], "paracetamol": ["acetaminophen", "crocin", "dolo", "tylenol"],
    "lisinopril": [], "simvastatin": ["zocor"], "clarithromycin": [], "sildenafil": ["viagra"],
    "nitroglycerin": ["glyceryl trinitrate", "gtn"], "fluoxetine": ["prozac"], "tramadol": [],
    "clopidogrel": ["plavix"], "omeprazole": ["prilosec"], "metformin": ["glycomet"],
    "digoxin": [], "amiodarone": [],
}
DEMO_INTERACTIONS = [
    ("warfarin", "ibuprofen", "major", "Higher risk of serious bleeding, especially stomach bleeding."),
    ("warfarin", "aspirin", "major", "Higher risk of bleeding."),
    ("warfarin", "paracetamol", "moderate", "Regular use may raise INR and bleeding risk."),
    ("ibuprofen", "aspirin", "moderate", "Ibuprofen may weaken low-dose aspirin's heart protection; more stomach irritation."),
    ("lisinopril", "ibuprofen", "moderate", "NSAIDs can reduce blood-pressure control and strain the kidneys."),
    ("simvastatin", "clarithromycin", "major", "Raises simvastatin levels; risk of severe muscle damage."),
    ("sildenafil", "nitroglycerin", "major", "Can cause a dangerous drop in blood pressure. Do not combine."),
    ("fluoxetine", "tramadol", "major", "Risk of serotonin syndrome and seizures."),
    ("clopidogrel", "omeprazole", "moderate", "Omeprazole can reduce clopidogrel's effect."),
    ("digoxin", "amiodarone", "major", "Raises digoxin levels; risk of toxicity."),
]


def connect():
    db = sqlite3.connect(DB)
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(SCHEMA)
    columns = {r[1] for r in db.execute("PRAGMA table_info(interaction)")}
    if "source_id" not in columns:
        db.execute("ALTER TABLE interaction ADD COLUMN source_id INTEGER REFERENCES data_source(id)")
    if "source_record_id" not in columns:
        db.execute("ALTER TABLE interaction ADD COLUMN source_record_id TEXT")
    return db


def register_source(db, name, release, source_file, sha256, source_url=None, license_note=None):
    db.execute("""INSERT OR IGNORE INTO data_source
                  (name, release, source_file, sha256, source_url, license_note)
                  VALUES(?,?,?,?,?,?)""",
               (name, release, source_file, sha256, source_url, license_note))
    return db.execute("""SELECT id FROM data_source
                         WHERE name=? AND release=? AND source_file=? AND sha256=?""",
                      (name, release, source_file, sha256)).fetchone()[0]


def add_drug(db, name, aliases=()):
    name = name.strip().lower()
    db.execute("INSERT OR IGNORE INTO drug(name) VALUES(?)", (name,))
    did = db.execute("SELECT id FROM drug WHERE name=?", (name,)).fetchone()[0]
    for al in (name, *aliases):
        db.execute("INSERT OR IGNORE INTO alias VALUES(?,?)", (al.lower(), did))
    return did


def add_interaction(db, ida, idb, sev, note="", source_id=None, source_record_id=None):
    if ida == idb:
        return
    a, b = sorted((ida, idb))
    sev = sev.lower() if sev and sev.lower() in ("major", "moderate", "minor") else "unknown"
    db.execute("""INSERT OR REPLACE INTO interaction
                  (a, b, severity, note, source_id, source_record_id)
                  VALUES(?,?,?,?,?,?)""",
               (a, b, sev, note, source_id, source_record_id))


def init():
    db = connect()
    demo_source = register_source(db, "MedLite demo", "synthetic-demo-v1", "built-in",
                                  "not-applicable", license_note="Synthetic demonstration records; do not use clinically.")
    ids = {n: add_drug(db, n, al) for n, al in DEMO_DRUGS.items()}
    for x, y, sev, note in DEMO_INTERACTIONS:
        add_interaction(db, ids[x], ids[y], sev, note, demo_source, "demo")
    db.commit()
    print("Created", DB, "with DEMO data. Use `load` for the real DDInter data.")


# Brand/alternate names -> generic name as DDInter spells it (lowercase).
ALIASES = {
    "acetaminophen": ["paracetamol", "crocin", "dolo", "calpol", "tylenol"],
    "acetylsalicylic acid": ["aspirin", "ecosprin", "disprin"],
    "ibuprofen": ["brufen", "advil", "motrin"],
    "metformin": ["glycomet", "glucophage"],
    "warfarin": ["coumadin"], "simvastatin": ["zocor"], "atorvastatin": ["lipitor"],
    "amlodipine": ["norvasc"], "fluoxetine": ["prozac"], "clopidogrel": ["plavix"],
    "omeprazole": ["prilosec"], "sildenafil": ["viagra"],
}


def add_aliases(db):
    missing = []
    for generic, brands in ALIASES.items():
        row = db.execute("SELECT id FROM drug WHERE name=?", (generic,)).fetchone()
        if not row:
            missing.append(generic)
            continue
        for b in brands:
            db.execute("INSERT OR IGNORE INTO alias VALUES(?,?)", (b, row[0]))
    if missing:
        print("Note: not found in this data (alias skipped):", ", ".join(missing))


def load_csv(path, release="unspecified", source_url="https://ddinter.scbdd.com/download/", license_note="DDInter CC BY-NC-SA 4.0; attribution, noncommercial use, and share-alike terms apply; see https://ddinter.scbdd.com/terms/."):
    """Import one DDInter CSV while recording its file hash and release metadata."""
    db = connect()
    digest = hashlib.sha256()
    with open(path, "rb") as raw:
        for block in iter(lambda: raw.read(1024 * 1024), b""):
            digest.update(block)
    source_id = register_source(db, "DDInter", release, os.path.basename(path), digest.hexdigest(),
                                source_url, license_note)
    with open(path, newline="", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        cols = rd.fieldnames or []
        low = {c: c.lower().replace(" ", "_") for c in cols}
        ca = next((c for c in cols if re.fullmatch(r"drug(name)?_?(name_)?a", low[c])), None)
        cb = next((c for c in cols if re.fullmatch(r"drug(name)?_?(name_)?b", low[c])), None)
        cida = next((c for c in cols if low[c] in ("ddinterid_a", "drug_id_a", "id_a")), None)
        cidb = next((c for c in cols if low[c] in ("ddinterid_b", "drug_id_b", "id_b")), None)
        cl = next((c for c in cols if "level" in low[c] or "sever" in low[c]), None)
        if not (ca and cb):
            sys.exit(f"Could not find drug A/B columns. Headers are: {cols}")
        cache, n = {}, 0
        for row in rd:
            ids = []
            for c in (ca, cb):
                nm = row[c].strip().lower()
                if nm not in cache:
                    cache[nm] = add_drug(db, nm)
                ids.append(cache[nm])
            source_record = "|".join(((row.get(cida) or "").strip() if cida else "",
                                      (row.get(cidb) or "").strip() if cidb else "")).strip("|") or None
            add_interaction(db, ids[0], ids[1], row.get(cl, "") if cl else "", "",
                            source_id, source_record)
            n += 1
    add_aliases(db)
    db.commit()
    print(f"Imported {n} rows ({len(cache)} drugs) from {os.path.basename(path)}.")
    print(f"Source: DDInter {release}; SHA-256 {digest.hexdigest()}")


def find_drugs(db, text, accepted_suggestions=()):
    """Find exact aliases and return fuzzy candidates for explicit user confirmation."""
    amap = dict(db.execute("SELECT alias, drug_id FROM alias"))
    words = re.findall(r"[a-z0-9]+", text.lower())
    used, found = set(), []
    for n in (4, 3, 2, 1):
        for i in range(len(words) - n + 1):
            if used & set(range(i, i + n)):
                continue
            did = amap.get(" ".join(words[i:i + n]))
            if did and did not in found:
                found.append(did)
                used |= set(range(i, i + n))
    corrections, suggestions, accepted_used = [], [], []
    if FUZZY:   # suggestions are never treated as medicines without confirmation
        singles = None
        confirmed = set()
        for value in accepted_suggestions:
            if not isinstance(value, dict):
                continue
            try:
                confirmed.add((str(value["input"]).lower(), int(value["drug_id"])))
            except (KeyError, TypeError, ValueError):
                continue
        for i, w in enumerate(words):
            if i in used or len(w) < 6 or not w.isalpha():
                continue
            if singles is None:
                singles = [x for x in amap if x.isalpha() and len(x) >= 5]
            cands = [x for x in singles if x[0] == w[0] and abs(len(x) - len(w)) <= 2]
            ranked = sorted(((difflib.SequenceMatcher(None, w, x).ratio(), x) for x in cands), reverse=True)
            best_by_drug = {}
            for score, alias in ranked:
                did = amap[alias]
                if score >= 0.84 and did not in best_by_drug:
                    best_by_drug[did] = {"drug_id": did, "name": drug_name(db, did),
                                         "alias": alias, "score": round(score, 3)}
            options = sorted((option for did, option in best_by_drug.items() if did not in found),
                             key=lambda item: (-item["score"], item["name"]))[:3]
            chosen = next((option for option in options if (w, option["drug_id"]) in confirmed), None)
            if chosen and chosen["drug_id"] not in found:
                found.append(chosen["drug_id"])
                used.add(i)
                corrections.append((w, chosen["name"]))
                accepted_used.append({"input": w, "drug_id": chosen["drug_id"]})
            elif options:
                suggestions.append({"input": w, "options": options})
    return found, corrections, suggestions, accepted_used


def drug_name(db, did):
    return db.execute("SELECT name FROM drug WHERE id=?", (did,)).fetchone()[0]


def lookup(db, ids):
    sql = f"""SELECT d1.name, d2.name, i.severity, i.note,
                     ds.name, ds.release, ds.source_file, ds.source_url, i.source_record_id
              FROM interaction i
              JOIN drug d1 ON d1.id=i.a JOIN drug d2 ON d2.id=i.b
              LEFT JOIN data_source ds ON ds.id=i.source_id
              WHERE (i.a=? AND i.b=?) OR (i.a=? AND i.b=?)
              ORDER BY {SEV_ORDER}"""
    if len(ids) >= 2:
        rows = []
        for ida, idb in itertools.combinations(dict.fromkeys(ids), 2):
            row = db.execute(sql, (min(ida, idb), max(ida, idb), max(ida, idb), min(ida, idb))).fetchone()
            if row:
                rows.append(row)
        severity_rank = {"major": 0, "moderate": 1, "minor": 2, "unknown": 3}
        rows.sort(key=lambda row: severity_rank.get(row[2], 4))
        return rows
    if not ids:
        return []
    sql = f"""SELECT d1.name, d2.name, i.severity, i.note,
                     ds.name, ds.release, ds.source_file, ds.source_url, i.source_record_id
              FROM interaction i
              JOIN drug d1 ON d1.id=i.a JOIN drug d2 ON d2.id=i.b
              LEFT JOIN data_source ds ON ds.id=i.source_id
              WHERE i.a=? OR i.b=? ORDER BY {SEV_ORDER} LIMIT 5"""
    return db.execute(sql, (ids[0], ids[0])).fetchall()


def facts_text(rows):
    label = lambda v: "LISTED, SEVERITY NOT RATED" if v == "unknown" else v.upper()
    facts = []
    for row in rows:
        a, b, sev, note = row[:4]
        source_name, release, source_file, source_url, record_id = row[4:9]
        line = f"- {a} + {b}: {label(sev)}. {note or ''}".rstrip()
        if source_name:
            ref = f"{source_name} {release} ({source_file})"
            if record_id:
                ref += f", record {record_id}"
            if source_url:
                ref += f" — {source_url}"
            line += f" Source: {ref}."
        else:
            line += " Source: legacy record; import provenance was not recorded."
        facts.append(line)
    return "\n".join(facts)


def single_drug_facts(db, did, name):
    """One drug named: summarise instead of dumping a long list."""
    counts = dict(db.execute("SELECT severity, COUNT(*) FROM interaction WHERE a=? OR b=? GROUP BY severity",
                             (did, did)).fetchall())
    total = sum(counts.values())
    if not total:
        return (f"No interaction records for {name} were found in this database. "
                "This does not establish that the medicine is safe or has no interactions.")
    head = (f"{name} has {total} listed interactions: {counts.get('major', 0)} major, "
            f"{counts.get('moderate', 0)} moderate, {counts.get('minor', 0)} minor, "
            f"{counts.get('unknown', 0)} not rated.")
    top = facts_text(lookup(db, [did])[:5])
    return f"{head}\nTop results (most severe first):\n{top}\n\nTo check a specific combination, name your other medicines too."


def llm_summary(facts):
    facts = "\n".join(facts.splitlines()[:8])          # keep the prompt short for a tiny model
    prompt = ("Rewrite these drug-interaction facts as at most 3 short, simple sentences for a patient. "
              "Use ONLY the facts given. Do not add anything. Stop after 3 sentences.\n\n" + facts)
    body = {"model": MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": 0, "num_predict": 100, "repeat_penalty": 1.15}}  # hard cap: no runaway output
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", method="POST",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)["response"].strip()
    except Exception as e:
        return f"(model unavailable: {e.__class__.__name__}; is `ollama serve` running?)"


def stats():
    db = connect()
    nd = db.execute("SELECT COUNT(*) FROM drug").fetchone()[0]
    na = db.execute("SELECT COUNT(*) FROM alias").fetchone()[0]
    ni = db.execute("SELECT COUNT(*) FROM interaction").fetchone()[0]
    print(f"drugs: {nd}   aliases: {na}   interactions: {ni}")
    print("recorded source files:", db.execute("SELECT COUNT(*) FROM data_source").fetchone()[0])
    unattributed = db.execute("SELECT COUNT(*) FROM interaction WHERE source_id IS NULL").fetchone()[0]
    print("interactions without import provenance:", unattributed)
    for name, release, source_file, digest in db.execute(
            "SELECT name, release, source_file, sha256 FROM data_source ORDER BY name, release, source_file"):
        print(f"  source: {name} {release} / {source_file} / sha256:{digest[:12]}")
    for sev, c in db.execute(f"SELECT severity, COUNT(*) FROM interaction GROUP BY severity ORDER BY {SEV_ORDER}"):
        print(f"  {sev:9s} {c:7d}  ({100 * c / max(ni, 1):.1f}%)")
    print(f"db file size: {os.path.getsize(DB) / 1e6:.1f} MB")
    ids, _, _, _ = find_drugs(db, "warfarin acetaminophen ibuprofen aspirin")
    if len(ids) > 1:
        t = time.perf_counter()
        for _ in range(200):
            lookup(db, ids)
        print(f"pair lookup ({len(ids)} drugs): {(time.perf_counter() - t) / 200 * 1000:.2f} ms avg")
    print("index plan:", db.execute("EXPLAIN QUERY PLAN SELECT * FROM interaction WHERE a=? OR b=?", (1, 1)).fetchall())


def answer(question, accepted_suggestions=()):
    db = connect()
    ids, corrections, suggestions, accepted = find_drugs(db, question, accepted_suggestions)
    names = [drug_name(db, i) for i in ids]
    if not ids:
        res = {"found": [], "facts": "No known drug name recognised in your question."}
    else:
        rows = lookup(db, ids)
        record_cards = [
            {"drug_a": row[0], "drug_b": row[1], "severity": row[2], "note": row[3],
             "source_name": row[4], "source_release": row[5], "source_file": row[6],
             "source_url": row[7], "source_record_id": row[8]}
            for row in rows
        ]
        if rows and len(ids) == 1:
            facts = single_drug_facts(db, ids[0], names[0])
        elif len(ids) > 1:
            pair_lines = []
            found_pairs = {(row[0], row[1]) for row in rows}
            found_pairs |= {(b, a) for a, b in found_pairs}
            for ida, idb in itertools.combinations(ids, 2):
                a, b = drug_name(db, ida), drug_name(db, idb)
                if (a, b) in found_pairs:
                    pair = next(row for row in rows if {row[0], row[1]} == {a, b})
                    pair_lines.append(facts_text([pair]))
                else:
                    pair_lines.append(f"- {a} + {b}: No matching interaction record in this database. "
                                      "This does not establish that the combination is safe.")
            facts = "\n".join(pair_lines)
        else:
            facts = (f"No interaction records for {names[0]} were found in this database. "
                     "This does not establish that the medicine is safe or has no interactions.")
        all_pairs_listed = len(ids) > 1 and len(rows) == (len(ids) * (len(ids) - 1) // 2)
        res = {"found": names, "facts": facts,
               "interaction_records": record_cards,
               "summary": llm_summary(facts) if USE_LLM and rows and all_pairs_listed else None}
        if len(ids) == 1:
            counts = dict(db.execute("SELECT severity, COUNT(*) FROM interaction WHERE a=? OR b=? GROUP BY severity",
                                     (ids[0], ids[0])).fetchall())
            res["interaction_counts"] = {key: counts.get(key, 0) for key in ("major", "moderate", "minor", "unknown")}
            res["interaction_total"] = sum(counts.values())
        elif len(ids) > 1:
            known = {(row[0], row[1]) for row in rows}
            known |= {(b, a) for a, b in known}
            res["unlisted_pairs"] = [
                {"drug_a": drug_name(db, a), "drug_b": drug_name(db, b)}
                for a, b in itertools.combinations(ids, 2)
                if (drug_name(db, a), drug_name(db, b)) not in known
            ]
    if suggestions:
        res["facts"] += "\n\nPossible spelling matches were not checked. Confirm a suggestion or enter the medicine name again."
    res["corrections"] = [f"{a} -> {b}" for a, b in corrections]
    res["suggestions"] = suggestions
    res["accepted_suggestions"] = accepted
    res["database_sources"] = [
        {"name": name, "release": release, "url": url}
        for name, release, url in db.execute(
            "SELECT DISTINCT name, release, source_url FROM data_source ORDER BY name, release")
    ]
    res["disclaimer"] = DISCLAIMER
    if LOG_QUERIES:
        db.execute("INSERT INTO log(question, found, answer) VALUES(?,?,?)",
                   (question, ", ".join(names), res["facts"]))
    db.commit()
    db.close()
    return res


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#f5f7fb"><title>MedLite | Interaction reference</title><style>
:root{color-scheme:light;--bg:#f4f6fa;--surface:#fff;--ink:#17233b;--muted:#66738a;--line:#e3e8f0;--brand:#18665e;--brand-dark:#124c47;--soft:#edf7f5;--warn:#8b5b12;--warn-bg:#fff7e8;--shadow:0 12px 34px #263b5b0d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.shell{max-width:1040px;margin:auto;padding:28px 24px 54px}.topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:42px}.brand{display:flex;align-items:center;gap:12px;font-weight:750;font-size:18px;letter-spacing:-.3px}.mark{width:38px;height:38px;border-radius:12px;background:var(--brand);color:white;display:grid;place-items:center;font-size:20px}.local{font-size:12px;color:var(--muted);border:1px solid var(--line);background:var(--surface);padding:6px 10px;border-radius:999px}
.hero{max-width:740px;margin:0 auto 26px}.eyebrow{color:var(--brand);font-weight:700;font-size:12px;letter-spacing:1.3px;text-transform:uppercase}.hero h1{font-size:clamp(30px,5vw,43px);line-height:1.12;letter-spacing:-1.3px;margin:10px 0 12px}.hero p{font-size:16px;color:var(--muted);margin:0;max-width:680px}
.workspace{max-width:740px;margin:auto}.panel{background:var(--surface);border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow);padding:24px}.panel-title{font-weight:700;font-size:16px;margin:0 0 4px}.panel-hint{color:var(--muted);font-size:13px;margin:0 0 17px}.input-wrap{position:relative}textarea{display:block;width:100%;min-height:112px;resize:vertical;padding:15px 16px;border:1px solid #cfd8e4;border-radius:11px;background:var(--surface);color:var(--ink);font:inherit;font-size:15px;line-height:1.5;outline:none;transition:border .15s,box-shadow .15s}textarea:focus{border-color:var(--brand);box-shadow:0 0 0 3px #18665e1a}textarea::placeholder{color:#99a4b4}.actions{display:flex;align-items:center;gap:12px;margin-top:14px}.primary{border:0;border-radius:9px;background:var(--brand);color:white;padding:11px 19px;font:inherit;font-size:14px;font-weight:600;cursor:pointer}.primary:hover{background:var(--brand-dark)}.primary:disabled{opacity:.65;cursor:wait}.helper{font-size:12px;color:var(--muted)}
.safety{display:flex;gap:11px;align-items:flex-start;margin-top:16px;padding:12px 14px;border:1px solid #f0dfb8;background:var(--warn-bg);border-radius:10px;color:#684714;font-size:13px}.safety strong{display:block;margin-bottom:1px}.safety .icon{font-size:16px;line-height:1.35}
#out{margin-top:22px}.result-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin:0 0 14px}.result-head h2{font-size:19px;margin:0;letter-spacing:-.3px}.subtle{color:var(--muted);font-size:12px}.chips{display:flex;flex-wrap:wrap;gap:7px;margin:11px 0 18px}.chip{background:var(--soft);color:var(--brand-dark);border:1px solid #d5ebe6;border-radius:999px;padding:5px 10px;font-size:12px;font-weight:650}.metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin:16px 0}.metric{border:1px solid var(--line);background:#fbfcfe;border-radius:11px;padding:12px}.metric b{display:block;font-size:21px;line-height:1.2}.metric span{font-size:11px;color:var(--muted)}
.section-label{font-size:11px;letter-spacing:.9px;text-transform:uppercase;color:var(--muted);font-weight:750;margin:20px 0 9px}.record{border:1px solid var(--line);border-radius:12px;padding:14px 15px;margin:9px 0;background:var(--surface)}.record-top{display:flex;align-items:center;justify-content:space-between;gap:12px}.pair{font-weight:700;letter-spacing:-.1px}.badge{white-space:nowrap;border-radius:999px;padding:4px 9px;font-size:10px;font-weight:800;letter-spacing:.5px}.badge-major{background:#fff0ed;color:#a43e2d}.badge-moderate{background:#fff5dd;color:#805d10}.badge-minor{background:#eaf5ed;color:#317044}.badge-unknown{background:#eef1f5;color:#566276}.note{margin:8px 0 0;color:#45536a;font-size:13px}.source{margin:9px 0 0;color:var(--muted);font-size:11px;overflow-wrap:anywhere}.source a{color:var(--brand)}.empty{border:1px solid #f0dfb8;background:var(--warn-bg);color:#684714;padding:14px;border-radius:11px;font-size:13px}.status{border:1px solid var(--line);border-radius:11px;padding:13px 14px;color:var(--muted);background:#fbfcfe;font-size:13px}.notice{border:1px solid #f0dfb8;background:var(--warn-bg);color:#684714;border-radius:11px;padding:14px;margin:12px 0}.suggestion-btn{border:1px solid #b6d5cf;background:#fff;color:var(--brand-dark);padding:7px 10px;border-radius:8px;font:inherit;font-size:12px;font-weight:600;cursor:pointer;margin:9px 7px 0 0}.footer{max-width:740px;margin:20px auto 0;color:var(--muted);font-size:11px;line-height:1.6}.footer a{color:var(--brand)}.generated{border-left:3px solid var(--brand);padding:12px 14px;background:var(--soft);border-radius:0 9px 9px 0;font-size:13px}
@media(max-width:600px){.shell{padding:18px 14px 36px}.topbar{margin-bottom:30px}.panel{padding:18px 15px}.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.record-top{align-items:flex-start}.helper{display:none}}
@media(prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#111a24;--surface:#182331;--ink:#e8eef6;--muted:#a0afc1;--line:#2b3949;--brand:#69c4b1;--brand-dark:#91d7c8;--soft:#1d3938;--warn:#f1c976;--warn-bg:#352d1e;--shadow:0 12px 34px #0003}textarea{border-color:#3a4a5d}.metric,.status{background:#1b2837}.note{color:#c1ccda}.badge-major{background:#482b2a;color:#ffaaa0}.badge-moderate{background:#453a22;color:#f1cf78}.badge-minor{background:#203b2c;color:#9cdaad}.badge-unknown{background:#293544;color:#bfcbda}.suggestion-btn{background:#182331;color:var(--brand-dark)}}
</style></head><body><main class="shell"><header class="topbar"><div class="brand"><span class="mark">＋</span><span>MedLite</span></div><span class="local">LOCAL DATABASE · OFFLINE LOOKUP</span></header>
<section class="hero"><div class="eyebrow">Medication reference</div><h1>Check interaction records</h1><p>Look up known interaction entries for medicines in your list. Review each result and its source with a pharmacist or clinician.</p></section>
<section class="workspace"><div class="panel"><h2 class="panel-title">Your medicines</h2><p class="panel-hint">Enter generic names, brand names, or a sentence. Separate multiple medicines with commas or “and”.</p><textarea id="q" aria-label="Medicine names" placeholder="For example: warfarin, ibuprofen"></textarea><div class="actions"><button class="primary" id="check" onclick="go([])">Check records <span aria-hidden="true">→</span></button><span class="helper">Names are checked against the local medicine database.</span></div><div class="safety"><span class="icon" aria-hidden="true">ⓘ</span><div><strong>Information only</strong>A missing record does not mean a combination is safe. This tool does not assess your health or recommend treatment.</div></div></div><div id="out" aria-live="polite"></div></section>
<footer class="footer">Database content: <span id="dbsource">DDInter snapshot</span>. Interaction records may be incomplete or outdated. <span id="disclaimer">Use this information as a discussion aid, not a diagnosis or treatment decision.</span></footer></main><script>
const out=document.getElementById('out');
function el(tag,text,cls,parent=out){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;parent.appendChild(n);return n}
function sourceLine(r,parent){if(!r.source_name){el('div','Source provenance was not recorded for this entry.','source',parent);return}const box=el('div',undefined,'source',parent);let s=`Source: ${r.source_name} ${r.source_release||''}`.trim();if(r.source_file)s+=` · ${r.source_file}`;if(r.source_record_id)s+=` · Record ${r.source_record_id}`;box.appendChild(document.createTextNode(s+' · '));if(r.source_url){const a=document.createElement('a');a.href=r.source_url;a.target='_blank';a.rel='noopener noreferrer';a.textContent='View source';box.appendChild(a)}else box.appendChild(document.createTextNode('source link unavailable'))}
function card(r){const c=el('article',undefined,'record');const top=el('div',undefined,'record-top',c);el('div',`${r.drug_a} + ${r.drug_b}`,'pair',top);const sev=(r.severity||'unknown').toLowerCase();el('span',sev==='unknown'?'NOT RATED':sev.toUpperCase(),`badge badge-${sev}`,top);if(r.note)el('p',r.note,'note',c);sourceLine(r,c)}
function render(d){out.replaceChildren();if(d.corrections?.length){const n=el('div',undefined,'status');el('strong','Spelling confirmed: ',undefined,n);n.appendChild(document.createTextNode(d.corrections.join(', ')))}
if(d.found?.length){const h=el('div',undefined,'result-head');const title=el('div',undefined,undefined,h);el('h2','Lookup results',undefined,title);el('div',d.found.length===1?'One medicine recognised':`${d.found.length} medicines recognised`,'subtle',title);const chips=el('div',undefined,'chips');for(const name of d.found)el('span',name,'chip',chips)}
if(d.interaction_total!==undefined){const total=d.interaction_total;el('div',`Database records for ${d.found[0]}`,'section-label');if(total===0)el('div',`No interaction records were found for ${d.found[0]} in this database. That does not establish safety.`,'empty');else{const grid=el('div',undefined,'metric-grid');for(const [key,label] of [['major','Major'],['moderate','Moderate'],['minor','Minor'],['unknown','Not rated']]){const m=el('div',undefined,'metric',grid);el('b',d.interaction_counts?.[key]??0,undefined,m);el('span',label,undefined,m)}el('div',`Showing ${d.interaction_records.length} of ${total} listed records, ordered by database severity.`,'subtle');for(const r of d.interaction_records)card(r)}}
else if(d.found?.length){el('div','Pair-by-pair results','section-label');for(const r of d.interaction_records||[])card(r);for(const p of d.unlisted_pairs||[])el('div',`${p.drug_a} + ${p.drug_b}: No matching interaction record in this database. This does not establish safety.`,'empty');if(!(d.interaction_records?.length)&&!(d.unlisted_pairs?.length))el('div',d.facts,'status')}
else el('div',d.facts,'status');
for(const s of d.suggestions||[]){const n=el('div',undefined,'notice');el('strong',`Possible match for “${s.input}”`,'',n);el('div','Confirm the medicine name before checking its records.','subtle',n);for(const option of s.options){const b=el('button',`Use ${option.name}`,'suggestion-btn',n);b.onclick=()=>go([...(d.accepted_suggestions||[]),{input:s.input,drug_id:option.drug_id}])}}
if(d.summary){el('div','Optional plain-language summary','section-label');el('div',d.summary,'generated')}
if(d.database_sources?.length){document.getElementById('dbsource').textContent=d.database_sources.map(s=>`${s.name} ${s.release}`).join(', ')||'DDInter snapshot'}
}
async function go(accepted){const q=document.getElementById('q').value.trim();if(!q){out.replaceChildren();el('div','Enter at least one medicine name to search.','status');document.getElementById('q').focus();return}const b=document.getElementById('check');b.disabled=true;b.textContent='Checking…';out.replaceChildren();el('div','Searching the local interaction database…','status');try{const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q,accepted_suggestions:accepted})});if(!r.ok)throw new Error('Request failed');const d=await r.json();render(d);if(d.disclaimer)document.getElementById('disclaimer').textContent=d.disclaimer}catch(e){out.replaceChildren();el('div','Could not complete the lookup. Check that the local MedLite server is running, then try again.','empty')}finally{b.disabled=false;b.innerHTML='Check records <span aria-hidden="true">→</span>'}}
document.getElementById('q').addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key==='Enter')go([])});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(PAGE.encode(), "text/html; charset=utf-8")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(n) or b"{}")
        q = str(payload.get("q", ""))[:500]
        accepted = payload.get("accepted_suggestions", [])
        if not isinstance(accepted, list):
            accepted = []
        self._send(json.dumps(answer(q, accepted)).encode(), "application/json; charset=utf-8")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cmd = args[0] if args else ""
    if cmd == "init":
        init()
    elif cmd == "load" and len(args) > 1:
        raw_args = sys.argv[1:]
        release = "unspecified"
        if "--release" in raw_args:
            index = raw_args.index("--release")
            if index + 1 < len(raw_args):
                release = raw_args[index + 1]
        load_csv(args[1], release=release)
    elif cmd == "ask" and len(args) > 1:
        r = answer(" ".join(args[1:]))
        if r.get("corrections"):
            print("Confirmed spelling: " + ", ".join(r["corrections"]))
        print(("Recognised: " + ", ".join(r["found"]) + "\n" if r["found"] else "") + r["facts"])
        for suggestion in r.get("suggestions", []):
            options = ", ".join(option["name"] for option in suggestion["options"])
            print(f"\nPossible match for {suggestion['input']!r}: {options}. Re-run with the intended spelling to check it.")
        if r.get("summary"):
            print("\nSummary (AI):", r["summary"])
        print("\n" + r["disclaimer"])
    elif cmd == "stats":
        stats()
    elif cmd == "serve":
        connect().close()
        print("Open http://127.0.0.1:8000  (Ctrl+C to stop)")
        HTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
    else:
        print(__doc__)
