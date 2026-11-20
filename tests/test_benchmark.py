import csv
import json
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

import recognition_benchmark as bench

COLUMNS = ["example_id", "source_group", "split", "text", "mentions_json", "category",
           "provenance", "license_or_permission", "review_status"]


def mention(text, surface, normalized):
    start = text.index(surface)
    return {"start": start, "end": start + len(surface), "surface": surface, "normalized": normalized}


class Scorer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        text_a, text_b = "I take Coumadin daily.", "Advil and crocin."
        self.gold = self.write("gold.csv", COLUMNS, [
            ["e1", "g1", "validation", text_a, json.dumps([mention(text_a, "Coumadin", "warfarin")]), "brand",
             "test", "test", "draft"],
            ["e2", "g2", "validation", text_b, json.dumps([mention(text_b, "Advil", "ibuprofen"),
                                                            mention(text_b, "crocin", "acetaminophen")]),
             "multi-drug", "test", "test", "draft"],
        ])
        self.text_b = text_b

    def write(self, name, header, rows):
        path = Path(self.tmp.name) / name
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)
        return path

    def test_partial_prediction_scores(self):
        predictions = self.write("pred.csv", ["example_id", "mentions_json"], [
            ["e1", "[]"],
            ["e2", json.dumps([mention(self.text_b, "Advil", "ibuprofen")])],
        ])
        result = bench.score(self.gold, predictions, split="validation", allow_draft=True)
        self.assertEqual((result["micro"]["tp"], result["micro"]["fp"], result["micro"]["fn"]), (1, 0, 2))
        self.assertAlmostEqual(result["micro"]["recall"], 1 / 3)

    def test_draft_test_split_cannot_be_scored(self):
        with self.assertRaises(ValueError):
            bench.score(self.gold, self.gold, split="test", allow_draft=True)

    def test_committed_template_is_valid(self):
        rows = bench.read_csv(ROOT / "data" / "recognition_gold_template.csv")
        self.assertEqual(bench.validate(rows, strict=False), [])


if __name__ == "__main__":
    unittest.main()
