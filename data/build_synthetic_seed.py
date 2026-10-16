#!/usr/bin/env python3
"""Build a small, explicitly synthetic seed corpus with auditable offsets."""
import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "recognition_seed_draft.csv"
TAG = re.compile(r"\[\[(.+?)\|(.+?)\]\]")

# Groups stay wholly inside one split. These examples are seed material for
# pipeline development, not patient language and not a final benchmark.
EXAMPLES = [
    ("train-generic", "train", "generic", "I take [[ibuprofen|ibuprofen]] after lunch."),
    ("train-generic", "train", "generic", "Today I was prescribed [[metformin|metformin]]."),
    ("train-generic", "train", "generic", "My list says [[warfarin|warfarin]] once each evening."),
    ("train-generic", "train", "generic", "Please check the name [[amlodipine|amlodipine]] on this note."),
    ("train-brand", "train", "brand_alias", "My label says [[Crocin|acetaminophen]]."),
    ("train-brand", "train", "brand_alias", "I bought [[Advil|ibuprofen]] yesterday."),
    ("train-brand", "train", "brand_alias", "Does [[Glycomet|metformin]] appear in my list?"),
    ("train-brand", "train", "brand_alias", "The note mentions [[Coumadin|warfarin]]."),
    ("train-multidrug", "train", "multi_drug", "I take [[warfarin|warfarin]] with [[ibuprofen|ibuprofen]]."),
    ("train-multidrug", "train", "multi_drug", "My list includes [[metformin|metformin]], [[amlodipine|amlodipine]], and [[omeprazole|omeprazole]]."),
    ("train-multidrug", "train", "multi_drug", "Compare [[Crocin|acetaminophen]] and [[Brufen|ibuprofen]]."),
    ("train-multidrug", "train", "multi_drug", "The two names are [[fluoxetine|fluoxetine]] plus [[tramadol|tramadol]]."),
    ("train-negative", "train", "no_drug", "Headache since this morning, no medicine mentioned."),
    ("train-negative", "train", "no_drug", "Could stress cause nausea?"),
    ("train-negative", "train", "no_drug", "Please explain what an interaction means."),
    ("train-negative", "train", "no_drug", "I have a fever and feel tired."),
    ("validation-typo", "validation", "misspelling", "I took [[ibuprofin|ibuprofen]] after dinner."),
    ("validation-typo", "validation", "misspelling", "The spelling on my note is [[metformine|metformin]]."),
    ("validation-typo", "validation", "misspelling", "Can you recognize [[asprin|acetylsalicylic acid]]?"),
    ("validation-typo", "validation", "misspelling", "I use [[warfarine|warfarin]] every day."),
    ("validation-multiword", "validation", "multiword", "The record includes [[acetylsalicylic acid|acetylsalicylic acid]]."),
    ("validation-multiword", "validation", "multiword", "Please add [[activated charcoal|activated charcoal]] to the list."),
    ("validation-multiword", "validation", "multiword", "I found [[acetohydroxamic acid|acetohydroxamic acid]] on the label."),
    ("validation-multiword", "validation", "multiword", "Is [[acetylsalicylic acid|acetylsalicylic acid]] the same name as [[aspirin|acetylsalicylic acid]]?"),
    ("validation-phrase", "validation", "context", "I feel cold, but I have not named a medicine."),
    ("validation-phrase", "validation", "context", "Can medicine names be written in uppercase?"),
    ("validation-phrase", "validation", "context", "My headache started before I took anything."),
    ("validation-phrase", "validation", "context", "The word tablet appears here, but no specific drug does."),
    ("test-pairs", "test", "multi_drug", "I took [[Coumadin|warfarin]] and [[Advil|ibuprofen]] before bed."),
    ("test-pairs", "test", "multi_drug", "My note lists [[Plavix|clopidogrel]] plus [[Prilosec|omeprazole]]."),
    ("test-pairs", "test", "multi_drug", "Checking [[Viagra|sildenafil]] alongside [[nitroglycerin|nitroglycerin]]."),
    ("test-pairs", "test", "multi_drug", "The names are [[simvastatin|simvastatin]] and [[clarithromycin|clarithromycin]]."),
    ("test-negative", "test", "no_drug", "I woke up with a headache but took nothing."),
    ("test-negative", "test", "no_drug", "Could stress cause nausea?"),
    ("test-negative", "test", "no_drug", "This sentence does not name any medicines."),
    ("test-negative", "test", "no_drug", "I feel unwell and want general information."),
    ("test-multiword", "test", "multiword", "Please note [[acetylsalicylic acid|acetylsalicylic acid]]."),
    ("test-multiword", "test", "multiword", "Add [[activated charcoal|activated charcoal]] to the record."),
    ("test-multiword", "test", "multiword", "Does [[acetohydroxamic acid|acetohydroxamic acid]] appear here?"),
    ("test-multiword", "test", "multiword", "The label says [[acetylsalicylic acid|acetylsalicylic acid]], not aspirin."),
]


def annotate(marked_text):
    text_parts, mentions = [], []
    cursor = output_length = 0
    for match in TAG.finditer(marked_text):
        prefix = marked_text[cursor:match.start()]
        text_parts.append(prefix)
        output_length += len(prefix)
        surface, normalized = match.groups()
        start = output_length
        text_parts.append(surface)
        output_length += len(surface)
        mentions.append({"start": start, "end": output_length,
                         "surface": surface, "normalized": normalized})
        cursor = match.end()
    text_parts.append(marked_text[cursor:])
    return "".join(text_parts), mentions


def main():
    fields = ["example_id", "source_group", "split", "text", "mentions_json",
              "category", "provenance", "license_or_permission", "review_status"]
    with OUTPUT.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for index, (group, split, category, marked) in enumerate(EXAMPLES, start=1):
            text, mentions = annotate(marked)
            writer.writerow({
                "example_id": f"syn-{index:04d}", "source_group": group,
                "split": split, "text": text,
                "mentions_json": json.dumps(mentions, ensure_ascii=False),
                "category": category,
                "provenance": "Project-authored synthetic seed; no patient text.",
                "license_or_permission": "Synthetic project text; no external text copied.",
                "review_status": "draft-unreviewed",
            })
    print(f"Wrote {len(EXAMPLES)} synthetic draft examples to {OUTPUT}")


if __name__ == "__main__":
    main()
