# Medication mention annotation guide

Use this guide for a research dataset about identifying medicine names in short text. It is not a guide to clinical advice or interaction labeling.

## Unit and span rules

- One row is one sentence or short medication-list fragment.
- Annotate every explicit medicine name, including generic names, brand names, and clearly intended misspellings.
- Do not infer a medicine from symptoms, dose-taking language, or context alone. For example, “I have a headache” contains no medicine mention.
- Mark the exact visible characters. `start` is inclusive and `end` is exclusive, measured in Python Unicode string offsets. `surface` must equal `text[start:end]` exactly, including capitalization and punctuation inside a multiword name.
- Annotate repeated mentions separately. For multi-drug text, annotate each medicine span separately.
- Normalize to the canonical generic name used in the project inventory. Record brand names and spelling variants in `surface`; do not replace the surface with the normalized name.
- If a misspelling could refer to more than one medicine, mark the example for adjudication and exclude it from the scored set until resolved. Do not guess from a possible interaction.
- Do not label general health questions, symptoms, or ordinary words as medicine mentions unless the text explicitly uses a known medicine name.

## Review process

1. Two annotators independently fill their own blinded packet. Do not show them the current gold spans or each other’s answers.
2. Compare exact spans and normalized names. Discuss disagreements and record the adjudicated answer separately.
3. Set `review_status=approved` only after the annotations and source/usage rights are checked. Keep `draft-unreviewed` for generated or unresolved examples.
4. Keep paraphrases or related templates in one `source_group`; put each whole group in only one split. Do not tune thresholds or models on the test split.
5. Record source, license or permission, and whether text is synthetic or externally sourced. Do not use real patient messages without appropriate permission and review.

The current 40-row seed is synthetic and draft-only. Human review of that seed can check the annotation workflow, but it does not make the examples representative of patient language or independently authored.
