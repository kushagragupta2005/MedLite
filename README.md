# MedLite research workspace

This folder is a working copy for the lightweight drug-recognition study. The source files in Downloads were left unchanged.

## Contents

- `baseline/`: copied MedLite code, SQLite database, and the original evaluation artifacts.
- `data/`: copied DDInter CSV files and the annotation template. Confirm dataset terms and record source/license details before redistribution.
- `RESEARCH_PLAN.md`: task definition, metrics, baseline snapshot, and comparison protocol.
- `DATASET_OPTIONS.md`: external benchmark research, access conditions, and the recommended no-new-annotation evaluation route.
- `data/audit_medmentions.py` and `data/medmentions_audit.json`: reproducible format/split/offset audit and lexicon-overlap diagnostic for the locally downloaded corpus.
- `data/audit_smm4h2017_download.py` and `data/smm4h2017_download_audit.json`: read-only structural audit of the older `rxwfb3tysd-2` download. It checks ZIP integrity, row shapes, class counts, duplicates, and malformed/header-like rows without retrieving tweets or changing the Downloads files.

## Reproduce the current smoke test

```sh
cd baseline
python3 eval.py
```

This writes `results.csv` and `verify.csv` in `baseline/`. The checked-in CSVs are older artifacts from before the current evaluator format; regenerate them before using them. The built-in cases are not a held-out benchmark and their scores must not be reported as real-world performance. The current fuzzy column measures top suggestion after simulated user confirmation; it is not silent automatic correction.

## Safer database workflow now in the working copy

- The database path is anchored beside `med.py`; set `MEDLITE_DB` to choose another database.
- Importing a DDInter CSV stores the local filename, SHA-256, source URL, release label, and DDInter row IDs. Example: `python3 med.py load ../data/ddinter_downloads_code_A.csv --release local-export-2026-10-11`. Use a release label that accurately describes your downloaded snapshot; this example labels the local export date, not an official DDInter release.
- The browser suggests close spellings and waits for the user to confirm a candidate before checking it. Unconfirmed candidates are excluded from interaction lookup.
- Multi-medicine checks show a result for every pair, including pairs with no matching record.
- Raw query logging is disabled by default. To explicitly enable it for a local study, set `MEDLITE_LOG_QUERIES=1` before starting the app.
- On databases that predate provenance tracking, old records remain unattributed until their source files are re-imported; `stats` shows the count. The current imported snapshot has no unattributed interaction rows.

## Imported local snapshot

The research-copy database currently contains 1,939 drug names, 1,960 aliases, and 160,235 unique unordered interaction pairs. The SQLite file is about 14.1 MB. Eight local files were available and imported: `A`, `B`, `D`, `H`, `L`, `P`, `R`, and `V` (`ddinter_downloads_code_*.csv`). They contain 222,383 input rows; repeated unordered pairs collapse to one database row. A local audit found 43,826 repeated pairs across files and no severity-label disagreements among those repeated rows.

The DDInter site identifies its current database as release 1.0 (last update 2020-09-04) and lists the same eight CSV filenames; local byte sizes also match the page's rounded sizes. This supports that the local files correspond to the site's offered downloads. The site reports 1,972 approved drug entries, 1,833 distinct drugs, and 236,834 interaction drug pairs, which do not directly match the local import (1,939 drug names and 222,383 input rows). Resolve the count definitions before claiming comprehensive coverage. The database release label `local-export-2026-10-11` is a local label, not an official release identifier. [DDInter downloads](https://ddinter.scbdd.com/download/), [statistics](https://ddinter.scbdd.com/statistics/).

DDInter states its data are licensed under CC BY-NC-SA 4.0, with attribution, noncommercial-use, and share-alike terms. Its terms also say the data may be incomplete or contain errors, and that a missing interaction does not prove none exists. Keep that data license distinct from the project's code license and confirm the conditions before publishing the database or derived data. [DDInter terms](https://ddinter.scbdd.com/terms/). The `interaction` table keeps one source-row reference per unique pair, so repeated source rows are not all individually retained.

The copied database also already had 48 historical query-log rows. The new default prevents additional query logging, but those existing rows have been preserved in the working copy; review and clear them before publishing any database. The included `.gitignore` excludes the local database, its backups, the DDInter exports, and generated validation predictions from accidental commits. The Downloads originals were not changed.

DDInter files contain interaction level labels but may not contain a patient-friendly explanation for each pair. The app reports the stored level and source and does not generate a mechanism or treatment recommendation from the severity alone.

`baseline/audit_ddinter.py` recreates the local file/hash/pair audit and writes `data/ddinter_audit.json`. `data/ANNOTATION_GUIDE.md` defines the labeling rules, and `data/prepare_review_packets.py` creates two shuffled, blinded review sheets with no gold spans or split labels. The current review packets are only a workflow pilot for the synthetic seed. Keep `coordinator_key.csv` private until both reviewers finish.

## Data annotation format

`data/recognition_gold_template.csv` gives one row per sentence. `mentions_json` is a JSON list of mentions with character offsets (`start` inclusive, `end` exclusive), exact `surface` text, and the gold `normalized` generic name. Use `source_group` to keep related templates and paraphrases together when splitting. Use only synthetic, properly licensed, or appropriately approved text.

`data/build_synthetic_seed.py` creates a 40-sentence project-authored synthetic seed with spans generated from explicit tags. It is marked draft and unreviewed, and is only for developing the pipeline. `baseline/recognition_baseline.py` provides a span-aware exact dictionary baseline and a separate top-1 fuzzy suggestion mode that assumes explicit user confirmation. `baseline/recognition_benchmark.py` validates span offsets, source/license fields, review status, and source-group split leakage. Its scorer reports exact-span-plus-normalized-name micro precision, recall, F1, sentence exact match, and category breakdown; it scores `test` by default. Prediction files use `example_id,mentions_json` columns and one row per evaluated sentence, including `[]` for no predicted mentions. `--allow-draft` permits train/validation diagnostics only; draft test scoring is blocked.

The review packets are a workflow pilot, not a prerequisite for the external benchmark. The recommended next evaluation is BioCreative VII Task 3 / SMM4HDrug, which has gold medication spans and normalized names in naturally imbalanced social-media text. Its official files require registration and are delivered in batches. Report official-comparable span F1 separately from MedLite's stricter normalized-mention F1; see [`DATASET_OPTIONS.md`](DATASET_OPTIONS.md) and [`RESEARCH_PLAN.md`](RESEARCH_PLAN.md). MedMentions is downloaded locally but remains a PubMed chemical-text diagnostic, not a substitute for patient-style input.

The `rxwfb3tysd-2` folder in Downloads is the older SMM4H-2017 release. Its Subtasks 1 and 2 are tweet-ID classification sets without tweet text; Subtask 3 normalizes adverse-reaction expressions, not medicine mentions. Use it only for a separately scoped ADR/intake experiment if appropriate. Recreate its local audit with `python3 data/audit_smm4h2017_download.py ~/Downloads/rxwfb3tysd-2 --output data/smm4h2017_download_audit.json`. Do not run its old tweet-retrieval scripts or add this data to Git.

The MedMentions corpus file and official split lists are excluded from Git. After obtaining the same files from the [maintainer repository](https://github.com/chanzuckerberg/MedMentions), run `python3 data/audit_medmentions.py` to reproduce `data/medmentions_audit.json`. The current audit checks the 4,392 document IDs, official split coverage/overlap, T103 character offsets, and exact tokenized overlap with the local MedLite alias inventory. It deliberately does not calculate drug-recognition F1 because T103 covers chemicals beyond medicines and string overlap does not validate drug identity.

For the official SMM4H corpus, `data/import_smm4h.py` converts labeled train/validation TSVs into MedLite's gold format, maps known official normalized names through the existing alias table, and preserves unmapped names as explicit OOV gold labels. Example after obtaining the files: `python3 data/import_smm4h.py TRAIN.tsv data/smm4h_train.csv --split train` and the corresponding `--split validation` command. The importer refuses to label an unlabeled test file as gold.

For a CodaLab test submission, the exporter is ready at `baseline/smm4h_submission.py`. After obtaining the unlabeled test TSV through the official access route, run `python3 baseline/smm4h_submission.py PATH_TO_TEST.tsv PATH_TO_OUTPUT.zip`. It writes the official evaluator's tab-separated columns under `res/` inside the ZIP. `--fuzzy --fuzzy-threshold VALUE` enables automatic top-1 fuzzy predictions; select that threshold using training data only. The hidden test score is computed by CodaLab, not locally. Source tweet files, converted tables, and prediction archives are excluded from Git.

The first validation diagnostic is recorded in `baseline/validation_diagnostics_draft.json`: exact matching scored F1 0.714 and top-1 suggestions with simulated user confirmation scored F1 1.000 on 12 synthetic validation examples. This only shows that the prototype recovers the four deliberately seeded typos. Warm p95 was 0.090 ms exact and 1.614 ms for fuzzy candidate generation on this machine, excluding startup, UI, and confirmation time. These numbers are not real-world results; the test split remains unscored and is not an independent locked set.

```sh
cd baseline
python3 recognition_benchmark.py validate ../data/recognition_gold_template.csv --allow-draft
python3 ../data/build_synthetic_seed.py
python3 recognition_benchmark.py validate ../data/recognition_seed_draft.csv --allow-draft
python3 recognition_baseline.py predict ../data/recognition_seed_draft.csv validation_predictions.csv --split validation
python3 recognition_benchmark.py score ../data/recognition_seed_draft.csv validation_predictions.csv --split validation --allow-draft
python3 recognition_baseline.py latency ../data/recognition_seed_draft.csv --split validation --repeats 1000
python3 recognition_baseline.py predict ../data/recognition_seed_draft.csv validation_top1_confirmed.csv --split validation --top1-confirmed
python3 recognition_benchmark.py score ../data/recognition_seed_draft.csv validation_top1_confirmed.csv --split validation --allow-draft
python3 recognition_baseline.py latency ../data/recognition_seed_draft.csv --split validation --repeats 1000 --top1-confirmed
python3 ../data/prepare_review_packets.py
python3 audit_ddinter.py --data-dir ../data --database med.db --output ../data/ddinter_audit.json
```
