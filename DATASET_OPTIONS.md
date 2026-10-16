# External benchmark options for MedLite

Research checked 16 October 2026. The goal is to avoid asking people to annotate new text and instead use published gold annotations. No single public corpus exactly matches short, patient-style medication queries, so report source-specific results separately.

## Recommendation

Use the official SMM4H/BioCreative VII medication-mention corpus as the primary external benchmark. It directly annotates medication and supplement spans in informal social-media text and provides normalized names on labeled data. Registration is required; files are sent in batches to comply with Twitter limits. A crucial constraint: the released test inputs are unlabeled. Local scoring is possible on training/validation only; final held-out span scoring must use the still-open CodaLab post-evaluation server and requires a signed-in account. Do not claim a local test F1 or silently treat validation as test. The original task evaluates span extraction, not normalization, so report official leaderboard span F1 separately from any strict span-plus-normalization metric calculated on labeled validation data.

For work that can begin without requesting social-media data, MedMentions ST21pv is downloaded locally and audited as a **separate out-of-domain corpus/lexicon diagnostic**. It is CC0 and has fixed train/dev/test document splits, but it consists of PubMed titles and abstracts and annotates biomedical concepts broadly; it cannot establish performance on user queries. The audit found exact tokenized overlap between 2,356 of 37,401 T103 chemical mentions and the current MedLite alias list (6.30%). This is overlap/coverage only, not model F1 or proof that the matching mentions are medicines. BC5CDR is another literature-domain cross-check, but it has the same domain mismatch and its corpus terms should be checked at the source before reuse.

## Acquisition status and handoff

I searched the local Downloads folder for SMM4H/BioCreative/medication corpus files and found only the SMM4H-2017 `rxwfb3tysd-2` package. The BioCreative VII paper says SMM4HDrug is available from the task page and describes its train/validation/test split and span labels. A historical organizer response on the CodaLab forum says Task 3 registration was handled through BioCreative and the TSV files were sent after registration; the paper also says organizers continued to provide train and unlabeled test data on request. The task page did not load in the current web retrieval, so I cannot verify whether the access process has since changed. [Task paper](https://academic.oup.com/database/article/doi/10.1093/database/baac108/7025388), [organizer's CodaLab response](https://competitions.codalab.org/forums/20621/5774/).

The local importer and prediction packager are already prepared. When the official files become available, save them outside Git or under ignored `data/` paths, then run:

```sh
python3 data/import_smm4h.py TRAIN.tsv data/smm4h_train.csv --split train
python3 data/import_smm4h.py VALIDATION.tsv data/smm4h_validation.csv --split validation
```

Review the generated summary JSON for unmapped official names before fitting/tuning. Do not create labels for the unlabeled test file. Preserve the source split and tweet text locally according to the access terms; send frozen test predictions through the official evaluator.

## Verified sources

| Corpus | What the primary source says | Fit for MedLite | Access / use decision |
|---|---|---|---|
| SMM4HDrug / BioCreative VII Task 3 | 181,607 tweets from 212 timelines; 442 posts contain medication or supplement mentions (about 0.2%). Labeled rows provide character spans and normalized names. Published split: train 218 positive / 88,770 negative, validation 93 / 38,044, test 131 / 54,351. | **Best match** for informal user-generated medication mentions, ambiguity, colloquial forms and realistic negative prevalence. Twitter timelines and pregnancy-related selection still do not equal a general health-assistant query distribution. The official task is span extraction; MedLite's normalization task is additional. | Registration is required; the official page distributes data in batches. The test input file contains only tweet IDs and text, without gold spans; the post-evaluation CodaLab competition is marked open indefinitely and requires sign-in to participate. Thus local train/validation scores are possible after access, while final test span scoring is server-side. [Official task page](https://biocreative.bioinformatics.udel.edu/tasks/biocreative-vii/track-3/), [CodaLab competition status](https://competitions.codalab.org/competitions/23925), [task paper](https://academic.oup.com/database/article/doi/10.1093/database/baac108/7025388). |
| SMM4HBalancedDrug | 9,622 manually annotated posts (4,975 positive / 4,647 negative) made available as development/training support in the shared task. | Useful for development or training because it supplies more positive examples; its balanced sampling is not a deployment-prevalence test. Confirm that the downloaded release includes the span and normalization fields required by the current scorer. | Distributed through the shared-task route. Do not substitute its balanced distribution for the naturally sparse SMM4HDrug test. [Task paper](https://academic.oup.com/database/article/doi/10.1093/database/baac108/7025388). |
| MedMentions ST21pv | 4,392 PubMed papers; 203,282 entity mentions in the ST21pv subset. PubTator annotations include character start/end offsets, semantic types, and UMLS concept identifiers. The maintainers state the corpus is CC0. T103 is the Chemical semantic type; the subset includes source vocabularies such as RxNorm, NDDF and NDFRT. | Downloaded and structurally audited locally. Exact tokenized overlap: 2,356 of 37,401 T103 mention spans (6.30%) occur in the current MedLite alias lexicon. This is a lexical overlap statistic only; it is not precision, recall, F1, or verified medicine coverage. The corpus includes non-drug chemicals and biomedical papers, so it is not a patient-language benchmark. | Public corpus and official document split lists are hosted by the maintainers. Keep its corpus/profile results separate from SMM4H results. [Maintainer README](https://github.com/chanzuckerberg/MedMentions), [ST21pv documentation](https://github.com/chanzuckerberg/MedMentions/tree/master/st21pv). |
| BC5CDR | 1,500 PubMed articles with chemical/disease entity annotations and chemical–disease relations; chemical IDs are MeSH. | A compact standard NER cross-check for chemical spans. Chemicals are not synonymous with medications, and abstracts are unlike user queries. | Public corpus release and secondary loaders exist; verify the organizer's corpus-use terms before bundling or redistributing. Report only as literature-domain chemical-mention performance. [Corpus release](https://github.com/JHnlp/BioCreative-V-CDR-Corpus), [corpus paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC4860626/). |
| 2018 n2c2 medication extraction | Medication entities, signature details and adverse drug events in clinical narratives. | More clinical-document context, but EHR notes are not conversational queries and the task includes fields beyond drug mention recognition. | Credentialed challenge data with controlled access; not a self-service public corpus. Do not use without the required approval and terms. [Challenge paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC7489085/). |

## Assessment of the newly downloaded SMM4H-2017 package

The `~/Downloads/rxwfb3tysd-2` package is the latest (v2) SMM4H-2017 release, but it does not provide the medication-mention span benchmark needed by MedLite. Subtasks 1 and 2 contain tweet IDs, user IDs, and classification labels without tweet text. Subtask 3 maps adverse-reaction expressions to MedDRA terms, a different recognition/normalization task. The three ZIP archives pass integrity checks and the row totals align with the README descriptions; the audit found one duplicate ID in Subtask 1 training set 1, one five-field merged row in Subtask 3 training set 4, and one header-like row inside the Subtask 3 evaluation file. The old retrieval scripts are not part of the workflow. The Mendeley landing page lists CC BY 4.0, while the included README files warn against redistributing tweets, annotations, or the corpus under Twitter terms. Keep this package local and do not publish its contents until that discrepancy and applicable terms are resolved. [Mendeley Data v2](https://data.mendeley.com/datasets/rxwfb3tysd/2), [SMM4H-2017 paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC6188524/).

The read-only audit is reproducible with `python3 data/audit_smm4h2017_download.py ~/Downloads/rxwfb3tysd-2 --output data/smm4h2017_download_audit.json`. The original download is left untouched. Do not feed these files to `data/import_smm4h.py`: that importer expects the later SMM4HDrug labeled format with tweet text and medication span fields.

**Decision:** keep DDInter for interaction facts and proceed with BioCreative VII Task 3 / SMM4HDrug for the primary medication recognizer benchmark. The 2017 Subtask 3 may be explored later as a distinct adverse-reaction normalization side experiment, after filtering/repairing a working copy and reporting it under its own task definition.

## Evaluation plan without new human annotation

1. Keep MedLite's existing synthetic examples as development diagnostics only; do not use their draft test split as the headline result.
2. Register through the official BioCreative route and obtain labeled train/validation files plus unlabeled test inputs. Preserve supplied splits and source IDs.
3. Compare exact dictionary and fuzzy-suggestion modes locally on validation. Report official span-only F1; report span-plus-normalization only as a separate MedLite metric because normalization is not the shared-task test metric.
4. Tune only on training/validation, freeze model and thresholds, produce predictions in the official submission format, and use the CodaLab post-evaluation phase for blinded test span F1. The account is required for submission; test labels are not available for local scoring.
5. Report validation metrics separately from server-scored test metrics, including OOV rate and results by mention form where gold annotations permit. Preserve the natural imbalance; do not balance the held-out test input set.
6. Use the local MedMentions audit only as a separately named out-of-domain corpus/lexicon diagnostic. Do not compute or publish a MedLite drug-recognition F1 on the broad T103 label without a defensible medication-only mapping; do not compare or merge MedMentions results with SMM4HDrug.
7. Measure per-sentence warm median/p95, startup separately, and model-file size separately from the alias inventory and SQLite data.

## Why the dataset types must stay separate

DDInter is a drug-pair interaction knowledge base, not a mention corpus. BC5CDR and MedMentions label chemicals in scientific writing, not only medicines in personal queries. SMM4HDrug is the closest match to noisy user text but contains tweets and has extremely sparse positives. EHR corpora contain clinical shorthand and may require controlled access. Combining all of these into one F1 number would obscure what the recognizer actually handles.

## Sources checked

- Magge et al. (2023), “Automatic Extraction of Medication Mentions from Tweets—Overview of the BioCreative VII Shared Task 3 Competition,” *Database*, DOI: 10.1093/database/baac108.
- Official BioCreative VII Task 3 page: https://biocreative.bioinformatics.udel.edu/tasks/biocreative-vii/track-3/.
- Official Task 3 span evaluator (source inspected for submission columns and packaging): https://bitbucket.org/davy-weissenbacher/biocreativetask3evaluation/src/master/.
- CodaLab BioCreative'21 Task 3 post-evaluation status and leaderboard: https://competitions.codalab.org/competitions/23925.
- Mohan & Li (2019), “MedMentions: A Large Biomedical Corpus Annotated with UMLS Concepts,” AKBC 2019; maintainer repository README and ST21pv documentation.
- Local MedMentions file checksums, split counts, offset audit, and alias-overlap diagnostic: `data/medmentions_audit.json`; reproducible with `python3 data/audit_medmentions.py` after downloading the CC0 corpus files from the maintainer repository.
- Li et al. (2016), “BioCreative V CDR task corpus: a resource for chemical disease relation extraction,” *Database*, DOI: 10.1093/database/baw068.
- 2018 n2c2 shared-task overview, https://pmc.ncbi.nlm.nih.gov/articles/PMC7489085/.
