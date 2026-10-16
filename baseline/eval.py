#!/usr/bin/env python3
"""MedLite evaluation. Run in the same folder as med.py and med.db:  python3 eval.py

Part 1 - exact recognition vs top-1 fuzzy suggestions after simulated confirmation -> results.csv
Part 2 - hand-verification sheet for severity spot checks            -> verify.csv

NOTE: This small hand-written set is a smoke test, not a held-out benchmark. Part 1 measures
whether the right drugs are FOUND in a sentence; the fuzzy result assumes a person confirms
the top suggestion and is not automatic correction. It does not
check clinical correctness; that is what Part 2 (manual check on the DDInter
website) is for. Expected names use "a|b" when the data may spell a drug either way.
"""
import csv, statistics, time
import med

# (category, question, [expected drugs])
CASES = [
    ("brand",       "crocin",                                  ["acetaminophen"]),
    ("brand",       "dolo 650",                                ["acetaminophen"]),
    ("brand",       "tylenol",                                 ["acetaminophen"]),
    ("brand",       "viagra",                                  ["sildenafil"]),
    ("brand",       "I take Glycomet daily",                   ["metformin"]),
    ("brand",       "coumadin",                                ["warfarin"]),
    ("brand",       "ecosprin",                                ["acetylsalicylic acid|aspirin"]),
    ("brand",       "paracetamol",                             ["acetaminophen"]),
    ("multi-drug",  "I take crocin and brufen",                ["acetaminophen", "ibuprofen"]),
    ("multi-drug",  "tylenol and advil",                       ["acetaminophen", "ibuprofen"]),
    ("multi-drug",  "Glucophage with Zocor",                   ["metformin", "simvastatin"]),
    ("multi-drug",  "coumadin and prilosec",                   ["warfarin", "omeprazole"]),
    ("multi-drug",  "plavix and prozac",                       ["clopidogrel", "fluoxetine"]),
    ("multi-drug",  "atorvastatin, amlodipine and aspirin",    ["atorvastatin", "amlodipine", "acetylsalicylic acid|aspirin"]),
    ("multi-drug",  "warfarin, ibuprofen, paracetamol",        ["warfarin", "ibuprofen", "acetaminophen"]),
    ("format",      "PARACETAMOL AND IBUPROFEN",               ["acetaminophen", "ibuprofen"]),
    ("format",      "warfarin+ibuprofen",                      ["warfarin", "ibuprofen"]),
    ("format",      "WARFARIN!!!",                             ["warfarin"]),
    ("format",      "paracetamol,ibuprofen,warfarin",          ["acetaminophen", "ibuprofen", "warfarin"]),
    ("format",      "can I take ecosprin with warfarin?",      ["acetylsalicylic acid|aspirin", "warfarin"]),
    ("format",      "metformin and glycomet",                  ["metformin"]),
    ("negative",    "xyzmedicine123",                          []),
    ("negative",    "hello",                                   []),
    ("negative",    "what is the weather today",               []),
    ("negative",    "can I take it with food",                 []),
    ("negative",    "123",                                     []),
    ("negative",    "",                                        []),
    ("negative",    "I am taking tablets before breakfast",    []),
    ("negative",    "headache and fever since morning",        []),
    ("negative",    "please check my medicine list",           []),
    ("misspelling", "ibuprofin",                               ["ibuprofen"]),    # expected to fail: no fuzzy match yet
    ("misspelling", "paracetmol",                              ["acetaminophen"]),
    ("misspelling", "metformine and simvastatine",            ["metformin", "simvastatin"]),
    ("misspelling", "warfarine and asprin",                    ["warfarin", "acetylsalicylic acid|aspirin"]),
]

PAIRS = [("warfarin", "ibuprofen"), ("warfarin", "acetaminophen"), ("simvastatin", "clarithromycin"),
         ("fluoxetine", "tramadol"), ("clopidogrel", "omeprazole"), ("digoxin", "amiodarone"),
         ("sildenafil", "nitroglycerin"), ("lisinopril", "ibuprofen"), ("acetaminophen", "ibuprofen"),
         ("warfarin", "acetylsalicylic acid")]


def run(db, fuzzy, have):
    med.FUZZY = fuzzy
    in_db = lambda item: any(x in have for x in item.split("|"))
    out, tpv, fp_t, fn_t, times = [], 0, 0, 0, []
    for cat, q, expected in CASES:
        if not all(in_db(e) for e in expected):
            out.append((cat, q, expected, "", "SKIP", 0.0, ""))
            continue
        t = time.perf_counter()
        ids, corrections, suggestions, _ = med.find_drugs(db, q)
        suggestion_note = ""
        if fuzzy and suggestions:
            # This is a top-1 suggestion score: a person is assumed to confirm the suggestion.
            accepted = [{"input": s["input"], "drug_id": s["options"][0]["drug_id"]}
                        for s in suggestions if s["options"]]
            ids, corrections, _, _ = med.find_drugs(db, q, accepted)
            suggestion_note = "; ".join(f"{s['input']} -> {s['options'][0]['name']} (confirmation needed)"
                                         for s in suggestions if s["options"])
        if ids:
            med.lookup(db, ids)
        ms = (time.perf_counter() - t) * 1000
        times.append(ms)
        got = {db.execute("SELECT name FROM drug WHERE id=?", (i,)).fetchone()[0] for i in ids}
        allowed = {x for e in expected for x in e.split("|")}
        hit = sum(1 for e in expected if got & set(e.split("|")))
        fp = len(got - allowed)
        tpv += hit; fn_t += len(expected) - hit; fp_t += fp
        out.append((cat, q, expected, ", ".join(sorted(got)),
                    "PASS" if hit == len(expected) and fp == 0 else "FAIL", ms, suggestion_note))
    prec = tpv / max(tpv + fp_t, 1)
    rec = tpv / max(tpv + fn_t, 1)
    return out, prec, rec, times


def main():
    db = med.connect()
    have = {r[0] for r in db.execute("SELECT name FROM drug")}
    ex, pe, re_, te = run(db, False, have)
    fz, pf, rf, tf = run(db, True, have)
    med.FUZZY = True

    with open("results.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["category", "question", "expected", "exact_recognised", "exact_result",
                    "fuzzy_recognised_after_confirmation", "fuzzy_result", "fuzzy_ms",
                    "top1_suggestion_confirmation_required"])
        for a, b in zip(ex, fz):
            w.writerow([a[0], a[1], "|".join(a[2]), a[3], a[4], b[3], b[4], f"{b[5]:.2f}", b[6]])

    score = lambda rows, cat: (sum(r[4] == "PASS" for r in rows if r[0] == cat),
                               sum(r[4] in ("PASS", "FAIL") for r in rows if r[0] == cat))
    print(f"{'category':12s} {'exact':>8s} {'top1+confirm':>13s}")
    for cat in dict.fromkeys(c for c, _, _ in CASES):
        (p1, t1), (p2, t2) = score(ex, cat), score(fz, cat)
        print(f"{cat:12s} {f'{p1}/{t1}':>8s} {f'{p2}/{t2}':>8s}")
    tot = lambda rows: (sum(r[4] == "PASS" for r in rows), sum(r[4] in ("PASS", "FAIL") for r in rows))
    print(f"\noverall      exact {tot(ex)[0]}/{tot(ex)[1]}   top1+confirm {tot(fz)[0]}/{tot(fz)[1]}   "
          f"({sum(r[4] == 'SKIP' for r in fz)} skipped)")
    print(f"precision    exact {pe:.2f}   top1+confirm {pf:.2f}")
    print(f"recall       exact {re_:.2f}   top1+confirm {rf:.2f}")
    if tf:
        print(f"lookup time  exact median {statistics.median(te):.2f} ms   top1+confirm median {statistics.median(tf):.2f} ms, max {max(tf):.2f} ms")
    print("\nFailures (top1 suggestion plus simulated confirmation):")
    for r in fz:
        if r[4] == "FAIL":
            print(f"  [{r[0]}] {r[1]!r}: expected {'|'.join(r[2])} got {r[3] or 'nothing'}")

    # Part 2: hand-verification sheet
    with open("verify.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["drug_a", "drug_b", "medlite_says", "ddinter_website_says", "match?"])
        for a, b in PAIRS:
            ids = [db.execute("SELECT id FROM drug WHERE name=?", (n,)).fetchone() for n in (a, b)]
            if not all(ids):
                w.writerow([a, b, "drug not in database", "", ""])
                continue
            x, y = sorted(i[0] for i in ids)
            r = db.execute("SELECT severity FROM interaction WHERE a=? AND b=?", (x, y)).fetchone()
            w.writerow([a, b, r[0] if r else "no interaction listed", "", ""])
    print("\nWrote results.csv and verify.csv. Fill the 'ddinter_website_says' column by hand.")


if __name__ == "__main__":
    main()
