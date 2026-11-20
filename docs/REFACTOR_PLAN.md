# MedLite refactor plan

Status: implemented on branch `refactor/medlite-package` (see "Outcome" at the end).

## Findings

Ranked by leverage: safety impact first, then how much other work each one blocks.

### F1. The app and the benchmark use two different drug-name matchers (safety bug)

`baseline/med.py:find_drugs` (what the app runs) and
`baseline/recognition_baseline.py:recognize` (what the benchmark scores) were
separate implementations. The app compared raw alias strings such as
`"amphotericin b (liposomal)"` against punctuation-free word n-grams, and only
looked at n-grams of up to 4 words. As a result:

* 253 of the 1,960 aliases in the local DDInter snapshot (13%) contain
  punctuation, and 20 have more than four tokens. The app could never match them.
* `"anti-inhibitor coagulant complex with warfarin"` recognised **only
  warfarin**. The user got a single-drug summary instead of the pair check
  they asked for, with no warning that a medicine was skipped.
* `"amphotericin b (liposomal)"` resolved to the different DDInter entry
  `amphotericin b`.
* The published recognition scores measured the benchmark matcher, not
  the code users actually run.

### F2. One 500-line module holds every layer

`med.py` contained the schema, migrations, demo data, the DDInter importer,
recognition, lookup, response building, the LLM client, about 120 lines of inline
HTML/CSS/JS, the HTTP server and the CLI. None of these could be tested on its own.

### F3. Configuration is read from `sys.argv` at import time and changed through module globals

`USE_LLM` and `FUZZY` were computed from `sys.argv` when `med` was imported.
`eval.py` switched modes by assigning `med.FUZZY = ...`. Importing `med` from
another script (benchmark, importers, audits) silently picked up that
script's command-line flags.

### F4. LLM output is shown without validation

Grounding was enforced only by the prompt. Nothing checked that the model's
summary avoided naming other drugs or changing a severity label.

### F5. The HTTP server fails on bad input

* Malformed JSON raised an exception, so the client got a dropped connection
  instead of an error.
* `Content-Length` was trusted without a size limit.
* Every path, including typos, served the page.
* The port was hard-coded.

### F6. No tests, no CI, broken quick-start references

* The repository had no automated tests or CI.
* The README told readers to validate `data/recognition_gold_template.csv`,
  but `.gitignore` (`/data/*.csv`) kept it out of the repository.
* The README pointed at audit JSON files that are only generated locally.
* It read as private working notes ("source files in Downloads were left
  unchanged").

### F7. Smaller issues

* `sys.path.insert` hacks in `data/*.py` to reach `med`.
* N+1 `drug_name` queries inside the answer and recognition loops.
* `.gitignore` had duplicated blocks.

## Plan

1. **Package.** Create `medlite/` (standard library only, Python 3.9+):
   * `config.py`: a `Settings` dataclass built from environment variables.
     Nothing reads `sys.argv` at import time.
   * `db.py`: schema, connection, migrations and write helpers.
   * `demo.py`: demo data.
   * `ingest.py`: DDInter CSV import and brand aliases.
   * `recognition.py`: **the single matcher (F1).** It tokenizes aliases
     the same way as input text, does a left-to-right longest match with no
     4-token cap, and returns spans. Fuzzy candidates come from one shared
     function: the app shows the top 3 for confirmation, and the benchmark
     scores the top 1.
   * `lookup.py`: pair and single-drug lookups.
   * `answer.py`: builds the response.
   * `llm.py`: grounded summary plus the output guardrail (F4).
   * `server.py` and `static/index.html`: hardened server (F5).
   * `cli.py` and `__main__.py`: argparse CLI.
2. **Compatibility.** Keep `baseline/med.py` as a thin shim, so documented
   commands (`python3 med.py serve`) and the research scripts keep working.
   Point the research scripts at the package API, with no global mutation.
3. **Guardrail (F4).**
   * Reject a summary that names any database drug other than the recognised ones.
   * Reject a summary that uses a severity label not present in the facts.
   * Reject a summary that is empty or longer than the sentence cap.
   * A rejected summary is replaced by a short notice. The database facts
     are always shown.
4. **Tests.**
   * Add a `unittest` suite with no network and no licensed data. It covers
     the import, recognition regressions from F1, "missing record is never
     safe" wording, the guardrail, server error handling, the CLI, and the
     benchmark scorer.
   * Add GitHub Actions on Python 3.9 and 3.12.
5. **Docs.**
   * Rewrite the README as a project README: quick start with demo data,
     architecture, safety design and evaluation.
   * Move the research narrative to `docs/RESEARCH_NOTES.md`.
   * Commit the gold template, which is project-authored.
   * Deduplicate `.gitignore`.

## Regression gate

Before the change, with the local DDInter snapshot:

* `eval.py` scored exact 30/34 and top-1+confirm 34/34, with precision 1.00.
* The synthetic validation benchmark gave the outputs recorded in the
  README.

After the change, all of these must be the same or better, and every new
test must pass.

## Outcome

All plan items are done. This is what was verified.

**Regression gate (local DDInter snapshot, 160,235 pairs):**
* `eval.py` printed output and `results.csv` are identical to before, except the
  timing column: exact 30/34, top-1+confirm 34/34, precision 1.00.
* Benchmark prediction files for the synthetic validation split are
  byte-identical in both exact and top-1 modes: F1 0.714 and 1.000.

**Behaviour fixed:**
* `"anti-inhibitor coagulant complex with warfarin"` now runs the pair check.
  Before, it returned only a warfarin summary.
* `"amphotericin b (liposomal) and warfarin"` now resolves to the liposomal
  entry. It reports that this exact formulation has no record, and that this
  does not establish safety. Before, it showed the record for plain
  `amphotericin b`.

**Tests:**
* 49 `unittest` tests pass on Python 3.9 and 3.14, with warnings treated as
  errors.
* Mutation checks confirm the suite catches the old matcher behaviour (5
  failures) and a disabled guardrail (3 failures).
* CI runs the suite plus a demo smoke test on 3.9 and 3.12.

**Manual checks:**
* The web UI was exercised in a browser against the real snapshot: a
  hyphenated name, a spelling suggestion, confirming it, and a MAJOR result.
* `pip install .` works and ships the static page.
* The SMM4H submission packager and importer were smoke-tested on synthetic
  TSVs.

**Issues found during implementation and fixed:**
* `data/recognition_gold_template.csv` used `\"` escaping, which is not valid
  CSV, so `validate` always failed on it. It is rewritten with standard CSV
  quoting and covered by a test.
* `recognition_benchmark.score()` printed its result instead of returning it.
  It now returns a dict and `main()` prints it.
* `eval.py` timings previously included rebuilding the alias map on every
  query. The index is now built once, so old and new timings are not
  comparable. The README says so.
* The DDInter importer registered a `data_source` row before checking the CSV
  headers. A rejected file now leaves no trace.

**Not changed (out of scope):**
* The research scripts' behaviour and outputs.
* `RESEARCH_PLAN.md` and `DATASET_OPTIONS.md`.
* The database schema. Existing `med.db` files open unchanged.
