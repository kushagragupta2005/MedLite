# MedLite lightweight drug recognition study

## Research question

Can a lightweight hybrid drug-name recognizer identify and normalize medicine mentions in realistic user text, while meeting a target of at least 0.95 entity-level F1, less than 10 ms median end-to-end recognition latency per sentence, and less than 10 MB of learned model files?

These are targets, not established results. Interaction checking and clinical correctness are separate from the recognition study.

## Task definition (v1)

Input: one short natural-language sentence or medication-list fragment.

Output: zero or more recognized medicine mentions. Each output mention has the exact character offsets in the input, the matched surface text, and a normalized generic name from the project drug inventory. An alias or spelling correction is allowed only when the gold annotation supports that normalization. Do not infer a medicine from a symptom or general context alone.

Scoring: a true positive requires both exact span boundaries and the correct normalized generic name. A wrong span or wrong normalized name counts as a false positive and the missed gold mention counts as a false negative. Compute micro precision, recall, and F1 over mentions. Also report sentence-level exact match and separate results for brand/alias, misspelling, multiword name, ambiguous text, multi-drug, and no-drug examples.

Latency: end-to-end recognition of one sentence on the named local device, including normalization, dictionary lookup, candidate generation, and learned-model inference. Exclude UI rendering, database interaction lookup, and startup; report those separately if measured. Report warm median and p95 over at least 1,000 repetitions and include sentence-length distribution and hardware/software details.

Model size: total on-disk size of learned parameters and their required tokenizer/configuration files. Report the drug inventory, alias dictionary, and interaction database separately; do not count them as learned-model bytes.

## Data and split rules

- Keep the test set locked until model selection is finished.
- Split by source/template group so paraphrases and copied templates cannot cross splits.
- Maintain a second challenge split with drug names held out from training where feasible; aliases for a held-out generic must not leak across splits.
- Include naturally phrased positive and negative examples, brand/generic forms, spelling errors, multiword names, ambiguous ordinary words, and multiple medicines in one sentence.
- Store one row per sentence in `data/recognition_gold_template.csv`; serialize mention annotations as JSON with character offsets and normalized names.
- Record provenance and usage rights for every source. Do not put real patient text in the dataset without appropriate consent and review.

## External benchmark decision (16 October 2026)

Do not create another manually annotated corpus as the next step. The best available match is the BioCreative VII Task 3 / SMM4HDrug tweet corpus: it contains informal user-written text, exact medication spans, normalized names, and the naturally sparse distribution (442 medication-positive tweets among 181,607). The official task page states that the data is sent in batches after registration to comply with Twitter's redistribution limits. It is therefore not a one-click download, but it does avoid asking people to annotate new examples. See [the task page](https://biocreative.bioinformatics.udel.edu/tasks/biocreative-vii/track-3/) and [the corpus paper](https://academic.oup.com/database/article/doi/10.1093/database/baac108/7025388).

This external benchmark tests recognition in social-media text, not general health questions or Indian patient queries. Its official evaluation is span extraction. Labeled training and validation data contain normalized names, but the released test inputs contain only tweet IDs and text. Once data access is available, tune using training data, use validation as an untouched local evaluation, and submit frozen predictions to the post-evaluation CodaLab server for a blinded test span score. Report strict span-plus-normalization F1 only on labeled validation data; it is not part of the official hidden test metric. Retain unmappable validation gold names in recall accounting and report OOV separately. The competition's published evaluator expects `tweet_id`, `user_id`, `created_at`, `text`, `start`, `end`, `span`, and `drug` columns; `baseline/smm4h_submission.py` now produces this structure in a CodaLab `res/` archive.

Keep the supplied splits unchanged. The competition paper says the split randomly samples tweets from timelines, so tweets from the same users can occur across splits; do not claim independent-user generalization. The CodaLab page currently marks its post-evaluation phase as indefinite, but requires sign-in to participate. See [competition status](https://competitions.codalab.org/competitions/23925) and [the official task page](https://biocreative.bioinformatics.udel.edu/tasks/biocreative-vii/track-3/).

MedMentions ST21pv is an openly released CC0 corpus and can support a separate PubMed chemical-mention diagnostic, but it is not an alternative primary benchmark: it annotates biomedical papers and a broader set of chemical concepts, not medicine mentions in personal queries. Only use it if the evaluation is explicitly named as an out-of-domain diagnostic and the chemical-to-MedLite mapping is defensible. Do not mix its score with SMM4H or call it user-query performance. [MedMentions maintainer repository](https://github.com/chanzuckerberg/MedMentions).

The public MedMentions ST21pv corpus and its official split lists have now been downloaded locally. The audit found 4,392 documents, 203,282 annotation rows, and 37,401 T103 Chemical mentions; the 2,635/878/879 train/dev/test PMID lists are disjoint, cover all documents, and all checked T103 spans match the PubTator text offsets. Of the T103 spans, 2,356 (6.30%) have an exact tokenized surface match in MedLite's current alias lexicon. This overlap is not a medication mapping and is not a recognition score. The data and SHA-256 are recorded in `data/medmentions_audit.json`; local corpus and split files are excluded from Git.

## Baseline snapshot

The original copied baseline is the dictionary plus automatic fuzzy matching, scored by `baseline/eval.py` on 34 hand-written cases. On this tiny, development-visible set, exact matching passed 30/34 cases (precision 1.00, recall 0.85, F1 0.92); automatic fuzzy matching passed 34/34 (precision/recall/F1 1.00). The earlier script reported a 0.70 ms fuzzy median (maximum 1.37 ms) for its recognition plus lookup operation on that machine.

These figures are smoke-test results only: the examples are hand-authored in the evaluator, there are only four misspelling cases, and this is not a held-out realistic benchmark. The current matcher is rule-based, so learned-model size is 0 MB; its drug/alias data and SQLite interaction database are separate assets. Do not present this as meeting the research targets. The working copy now surfaces fuzzy candidates for user confirmation. Its smoke-test evaluator reports top-1 suggestions under an explicit simulated-confirmation assumption.

## Planned comparison

1. Exact dictionary matcher.
2. Fuzzy candidate suggestions, with thresholds selected on validation data only and user confirmation required.
3. A conventional compact learned baseline (character n-gram TF-IDF plus a linear classifier or ranker), trained only on the training split.
4. A hybrid that uses exact/alias matching first and invokes the compact learned component for unresolved candidates.

Every system must use the same fixed train/validation/test examples, normalization inventory, scoring code, and latency protocol. Keep the test split untouched until final comparison.

## Current implementation status

The working copy records imported source filenames and hashes, asks users to confirm fuzzy candidates, reports every pair in a multi-drug query, and disables new raw query logging by default. The eight CSVs currently present in the copied data folder have been imported and labeled `local-export-2026-10-11`; this is a local label, not an official release identifier. The filenames and byte sizes match the eight downloads currently listed by DDInter. The snapshot has 1,939 drug names, 1,960 aliases, and 160,235 unique unordered pairs from 222,383 input rows. DDInter's statistics page reports 1,972 approved entries, 1,833 distinct drugs, and 236,834 interaction drug pairs. Resolve the count definitions before claiming comprehensive coverage. DDInter states CC BY-NC-SA 4.0 terms; attribute the source and check the noncommercial/share-alike conditions before publishing the data. One representative source row is retained per unique local pair.

The pre-existing database contained 48 query-log rows. They are preserved in the working copy, so clear or exclude them before publishing any database artifact. Existing interaction rows without import metadata are reported as legacy by `stats`.

The next pipeline stage is implemented: a span-aware exact dictionary baseline, a separate top-1 fuzzy suggestion baseline, a source-group split and annotation validator, an exact-span scorer, and a warm-latency measurement command are available. `data/build_synthetic_seed.py` produces 40 project-authored synthetic examples across train/validation/test groups (16/12/12). They are intentionally marked draft/unreviewed; only train/validation diagnostics are allowed, and draft test scoring is blocked.

On the 12-example synthetic validation split, exact matching had entity micro F1 0.714 (precision 1.000, recall 0.556); all four seeded misspellings were missed. Top-1 fuzzy suggestions with simulated user confirmation had diagnostic F1 1.000. This assumes every top suggestion is confirmed and is not a deployed automatic correction result. Warm p95 was 0.090 ms exact and 1.614 ms fuzzy on Apple Silicon/macOS 15.8/Python 3.9.6, over 12,000 calls per method; startup, UI, and confirmation time are excluded. See `baseline/validation_diagnostics_draft.json`. These numbers only validate the pipeline on synthetic examples and must not be presented as real-world performance. The test split is unscored and is not independently locked.

Next: stop the manual annotation packet workflow for the primary benchmark. Obtain labeled SMM4H training/validation data and unlabeled test inputs through the official route. The labeled-data importer is `data/import_smm4h.py`; it maps known official normalizations through the MedLite alias table and retains unmapped labels as OOV. The CodaLab prediction formatter is `baseline/smm4h_submission.py`; the official test TSV and a signed-in CodaLab account are still needed before a real submission can be scored. Tune on training only; use validation once for local span and strict normalization metrics, then submit frozen span predictions to CodaLab for the blinded test score. This server score cannot establish the project's strict normalized-name target because test gold normalization is not released. MedMentions is downloaded and audited, but its broad chemical labels do not support a valid drug-recognition score without a defensible medication-only mapping. Keep interaction lookup accuracy separate from entity-recognition scores. Do not report synthetic draft scores as real-world performance.

### Decision after auditing the latest Downloads folder

`~/Downloads/rxwfb3tysd-2` is the older SMM4H-2017 package, not the SMM4HDrug medication-span release. Its archive checks pass, but Subtasks 1 and 2 have no tweet text and Subtask 3 is ADR-to-MedDRA normalization. A reproducible read-only audit is saved at `data/smm4h2017_download_audit.json`; its script is `data/audit_smm4h2017_download.py`. Do not train or score the medicine recognizer on this package. The next meaningful benchmark action is to obtain the later BioCreative VII Task 3 labeled train/validation files and unlabeled test inputs through the official access route. Once they are available locally, run `data/import_smm4h.py` on train and validation, inspect OOV mappings, freeze the baseline, evaluate validation, then package official test predictions for CodaLab. Do not retrieve or redistribute the older tweet corpus.
