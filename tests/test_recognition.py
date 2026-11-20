import unittest

from helpers import demo_db, drug_id, punctuated_db

import recognition_baseline
from medlite.recognition import AliasIndex, find_drugs, fuzzy_candidates, recognize


class ExactMatching(unittest.TestCase):
    def setUp(self):
        self.db = punctuated_db()
        self.index = AliasIndex.from_db(self.db)

    def names(self, text):
        return [m.normalized for m in recognize(text, self.index)]

    def test_hyphenated_name_is_not_silently_dropped(self):
        # Regression: the old app recognised only "warfarin" here and skipped the pair check.
        self.assertEqual(self.names("anti-inhibitor coagulant complex with warfarin"),
                         ["anti-inhibitor coagulant complex", "warfarin"])

    def test_hyphen_can_be_typed_as_space(self):
        self.assertEqual(self.names("anti inhibitor coagulant complex"), ["anti-inhibitor coagulant complex"])

    def test_formulation_in_parentheses_resolves_to_its_own_entry(self):
        # Regression: the old app mapped this to the different entry "amphotericin b".
        self.assertEqual(self.names("amphotericin b (liposomal) and warfarin"),
                         ["amphotericin b (liposomal)", "warfarin"])
        self.assertEqual(self.names("amphotericin b and warfarin"), ["amphotericin b", "warfarin"])

    def test_names_longer_than_four_tokens(self):
        self.assertEqual(self.names("human botulinum neurotoxin a/b immune globulin"),
                         ["human botulinum neurotoxin a/b immune globulin"])

    def test_spans_point_at_the_typed_text(self):
        text = "Can I take Coumadin + Advil?"
        mentions = recognize(text, self.index)
        self.assertEqual([text[m.start:m.end] for m in mentions], ["Coumadin", "Advil"])
        self.assertEqual([m.normalized for m in mentions], ["warfarin", "ibuprofen"])

    def test_non_drug_text(self):
        for text in ("", "123", "headache and fever since morning", "please check my medicine list"):
            self.assertEqual(self.names(text), [], text)

    def test_duplicate_mentions_collapse_to_one_drug_in_the_app(self):
        result = find_drugs("metformin and glycomet", self.index)
        self.assertEqual(result.drug_ids, [drug_id(self.db, "metformin")])


class SpellingSuggestions(unittest.TestCase):
    def setUp(self):
        self.db = demo_db()
        self.index = AliasIndex.from_db(self.db)
        self.warfarin = drug_id(self.db, "warfarin")

    def test_misspelling_is_suggested_not_applied(self):
        result = find_drugs("warfarine and ibuprofen", self.index)
        self.assertEqual(result.drug_ids, [drug_id(self.db, "ibuprofen")])
        self.assertEqual(result.suggestions[0]["input"], "warfarine")
        self.assertEqual(result.suggestions[0]["options"][0]["drug_id"], self.warfarin)

    def test_confirmed_suggestion_is_applied(self):
        result = find_drugs("warfarine and ibuprofen", self.index,
                            [{"input": "warfarine", "drug_id": self.warfarin}])
        self.assertIn(self.warfarin, result.drug_ids)
        self.assertEqual(result.corrections, [("warfarine", "warfarin")])
        self.assertEqual(result.suggestions, [])

    def test_confirmation_for_a_drug_that_was_not_offered_is_ignored(self):
        tramadol = drug_id(self.db, "tramadol")
        result = find_drugs("warfarine", self.index, [{"input": "warfarine", "drug_id": tramadol}])
        self.assertNotIn(tramadol, result.drug_ids)
        self.assertTrue(result.suggestions)

    def test_malformed_confirmations_are_ignored(self):
        result = find_drugs("warfarine", self.index, ["x", {"input": "warfarine"}, {"drug_id": "nan"}, None])
        self.assertEqual(result.drug_ids, [])

    def test_short_words_are_never_fuzzily_matched(self):
        self.assertEqual(fuzzy_candidates("dolo", self.index), [])

    def test_exact_mode_offers_no_suggestions(self):
        self.assertEqual(find_drugs("warfarine", self.index, fuzzy=False).suggestions, [])

    def test_top1_mode_takes_the_best_candidate(self):
        mentions = recognize("warfarine", self.index, top1_fuzzy=True)
        self.assertEqual([(m.normalized, m.fuzzy) for m in mentions], [("warfarin", True)])


class OneMatcherForAppAndBenchmark(unittest.TestCase):
    """The benchmark must score the matcher the app actually runs."""

    def test_benchmark_and_app_agree(self):
        db = punctuated_db()
        index = AliasIndex.from_db(db)
        names = dict(db.execute("SELECT id, name FROM drug"))
        for text in ("anti-inhibitor coagulant complex with warfarin", "Coumadin + Advil",
                     "amphotericin b (liposomal)", "warfarine and asprin", "nothing here"):
            for top1 in (False, True):
                benchmark = [m["normalized"] for m in recognition_baseline.recognize(text, index, top1)]
                app = find_drugs(text, index, fuzzy=False).drug_ids if not top1 else None
                if app is not None:
                    self.assertEqual(list(dict.fromkeys(benchmark)), [names[i] for i in app], text)
                self.assertEqual(benchmark, [m.normalized for m in recognize(text, index, top1_fuzzy=top1)])


if __name__ == "__main__":
    unittest.main()
