# MedLite

[![tests](https://github.com/kushagragupta2005/MedLite/actions/workflows/tests.yml/badge.svg)](https://github.com/kushagragupta2005/MedLite/actions/workflows/tests.yml)

MedLite is an offline drug-interaction lookup. The database is the source of truth, and an
optional small local LLM only rewrites retrieved facts in plain language, behind an output guardrail.

> **Information tool only, not medical advice.** A missing record never means a combination is safe.

- **Data:** [DDInter](https://ddinter.scbdd.com/) exports imported into SQLite with file-level
  provenance: SHA-256, release label and DDInter record IDs for every interaction.
  The author's local snapshot holds 160,235 unique drug pairs and 1,939 drugs in a 14 MB indexed database.
- **Recognition:** generic names, brand names and free text. Misspellings produce *suggestions*
  that the user must confirm; they are never applied silently.
- **LLM:** optional ([Ollama](https://ollama.com), default `qwen2.5:0.5b`). Summaries are generated
  only when every requested pair has a record, and they are withheld when they fail the guardrail (below).
- **Privacy:** runs on `127.0.0.1` only, request logging is off, and raw questions are stored only if
  `MEDLITE_LOG_QUERIES=1` is set.
- **Dependencies:** standard-library Python 3.9+ only.

## Quick start

No licensed data is needed for a first look. `init` creates a small demo database.

```sh
python3 -m medlite init                                  # demo data -> baseline/med.db
python3 -m medlite ask "can I take coumadin with advil?"
python3 -m medlite serve                                 # http://127.0.0.1:8000
```

Use the real data by downloading the DDInter CSVs from <https://ddinter.scbdd.com/download/>
(CC BY-NC-SA 4.0) and importing them:

```sh
python3 -m medlite load data/ddinter_downloads_code_A.csv --release local-export-YYYY-MM-DD
python3 -m medlite stats
```

Options:
- `--db PATH` or `MEDLITE_DB` choose the database.
- `ask`/`serve --llm` enable the guarded summary (needs `ollama serve`).
- `--exact` turns off spelling suggestions.
- `serve --port N` changes the port.
- `MEDLITE_MODEL` and `MEDLITE_OLLAMA_URL` configure the model.

The older entry point `python3 baseline/med.py <command>` still works and runs the same code.

## How it works

```text
question ─▶ recognition ─▶ SQLite lookup ─▶ facts (+ source per record) ─▶ JSON / CLI
              │ exact spans          │ every pair reported,           │
              │ fuzzy = suggestion   │ "no record ≠ safe"             └▶ optional LLM summary
              ▼ (user confirms)      ▼                                    ─▶ guardrail ─▶ shown or withheld
```

| Module | Responsibility |
|---|---|
| `medlite/recognition.py` | **The one matcher** used by the app, the CLI *and* the benchmark: tokenized aliases, longest left-to-right match, confirm-before-use fuzzy candidates |
| `medlite/db.py`, `ingest.py`, `demo.py` | Schema and migrations, DDInter import with provenance, demo data |
| `medlite/lookup.py`, `answer.py` | Pair and single-drug queries, response building, missing-record wording |
| `medlite/llm.py` | Ollama client, grounded prompt, output guardrail |
| `medlite/server.py`, `static/index.html` | Local web UI and `POST /ask` |
| `medlite/cli.py` | `init`, `load`, `ask`, `stats`, `serve` |
| `baseline/` | Evaluation and benchmark scripts |
| `data/` | Annotation guide, corpus builders and dataset audits |

### LLM guardrail

The model gets at most eight fact lines, temperature 0, and a 100-token cap. Its output is
**withheld**, and only the database facts are shown, if any of these hold:

- it names a drug, by generic or brand name, other than the ones the user asked about;
- it uses a severity (major/moderate/minor) that does not appear in the facts;
- it is empty or longer than three sentences;
- the model is unavailable.

The UI and CLI say why a summary was withheld.

## Evaluation

```sh
python3 -m unittest discover -s tests -t tests      # 49 tests, no network or licensed data needed
```

CI runs the same suite on Python 3.9 and 3.12. Research evaluation needs a database built from
DDInter. Run it from `baseline/`:

```sh
cd baseline
python3 eval.py                                     # recognition smoke test -> results.csv, verify.csv
python3 ../data/build_synthetic_seed.py             # 40-sentence synthetic draft corpus
python3 recognition_baseline.py predict ../data/recognition_seed_draft.csv pred.csv --split validation
python3 recognition_benchmark.py score ../data/recognition_seed_draft.csv pred.csv --split validation --allow-draft
```

Current results, all from small project-authored sets. These are **not** clinical or real-world accuracy.

| Check | Exact | Top-1 suggestion + confirmation |
|---|---|---|
| `eval.py` smoke test (34 sentences) | 30/34, precision 1.00, recall 0.85 | 34/34 |
| Synthetic validation split (12 sentences), span F1 | 0.714 | 1.000 |

The next planned evaluation is the external BioCreative VII Task 3 / SMM4H medication benchmark.
The importer and CodaLab submission packager are already in `data/` and `baseline/`.
For the dataset audits, licensing details and the annotation workflow, see
[docs/RESEARCH_NOTES.md](docs/RESEARCH_NOTES.md) and [RESEARCH_PLAN.md](RESEARCH_PLAN.md).

The `eval.py` timings now build the alias index once, outside the timed loop.
Earlier timings included rebuilding it on every query, so the two sets of numbers are not comparable.

## Data and licence

- **Code:** [MIT](LICENSE).
- **DDInter data:** **CC BY-NC-SA 4.0** (attribution, noncommercial, share-alike). It is not
  redistributed here, and DDInter notes that its data may be incomplete. Databases, corpora and
  generated predictions are git-ignored.
- **What's committed:** only project-authored files (`data/recognition_gold_template.csv`, the
  synthetic seed builder).

See [docs/REFACTOR_PLAN.md](docs/REFACTOR_PLAN.md) for the 2026-11 restructuring and the
recognition bug it fixed.
