import unittest

from helpers import demo_db, punctuated_db

from medlite.answer import NO_DRUG_FOUND, build_answer
from medlite.config import Settings
from medlite.llm import check_summary


class FakeClient:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.prompts = reply, error, []

    def generate(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.reply


class Answers(unittest.TestCase):
    def setUp(self):
        self.db = demo_db()

    def ask(self, question, settings=None, **kwargs):
        return build_answer(self.db, question, settings=settings or Settings(), **kwargs)

    def test_listed_pair_returns_the_record_with_its_source(self):
        response = self.ask("Can I take coumadin with advil?")
        self.assertEqual(response["found"], ["warfarin", "ibuprofen"])
        self.assertIn("MAJOR", response["facts"])
        [record] = response["interaction_records"]
        self.assertEqual((record["severity"], record["source_name"]), ("major", "MedLite demo"))
        self.assertEqual(response["unlisted_pairs"], [])
        self.assertIsNone(response["summary"])

    def test_missing_pair_is_never_presented_as_safe(self):
        response = self.ask("metformin and digoxin")
        self.assertEqual(response["unlisted_pairs"], [{"drug_a": "metformin", "drug_b": "digoxin"}])
        self.assertIn("does not establish that the combination is safe", response["facts"])

    def test_every_pair_is_reported_for_three_drugs(self):
        response = self.ask("warfarin, ibuprofen and metformin")
        lines = response["facts"].splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(len(response["interaction_records"]) + len(response["unlisted_pairs"]), 3)

    def test_single_drug_gives_counts_and_top_records(self):
        response = self.ask("warfarin")
        self.assertEqual(response["interaction_counts"], {"major": 2, "moderate": 1, "minor": 0, "unknown": 0})
        self.assertEqual(response["interaction_total"], 3)
        self.assertIn("name your other medicines", response["facts"])

    def test_no_drug_recognised(self):
        response = self.ask("what is the weather today")
        self.assertEqual((response["found"], response["facts"]), ([], NO_DRUG_FOUND))
        self.assertIn("not medical advice", response["disclaimer"])

    def test_unconfirmed_suggestion_is_flagged_in_the_facts(self):
        response = self.ask("warfarine and ibuprofen")
        self.assertEqual(response["found"], ["ibuprofen"])
        self.assertIn("Possible spelling matches were not checked", response["facts"])

    def test_punctuated_names_reach_the_pair_check(self):
        self.db = punctuated_db()
        response = self.ask("anti-inhibitor coagulant complex with warfarin")
        self.assertEqual(response["found"], ["anti-inhibitor coagulant complex", "warfarin"])
        self.assertNotIn("interaction_total", response)       # a pair check, not a single-drug summary

    def test_questions_are_not_logged_unless_enabled(self):
        self.ask("warfarin and ibuprofen")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM log").fetchone()[0], 0)
        self.ask("warfarin and ibuprofen", Settings(log_queries=True))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM log").fetchone()[0], 1)


class GuardedSummary(unittest.TestCase):
    def setUp(self):
        self.db = demo_db()
        self.llm = Settings(use_llm=True)

    def ask(self, question, client):
        return build_answer(self.db, question, settings=self.llm, llm_client=client)

    def test_grounded_summary_is_shown(self):
        client = FakeClient("Warfarin and ibuprofen together raise the risk of serious bleeding.")
        response = self.ask("warfarin and ibuprofen", client)
        self.assertEqual(response["summary"], client.reply)
        self.assertIn("warfarin + ibuprofen: MAJOR", client.prompts[0])

    def test_summary_naming_an_unchecked_drug_is_withheld(self):
        client = FakeClient("Warfarin with ibuprofen is risky; try tramadol instead.")
        response = self.ask("warfarin and ibuprofen", client)
        self.assertIsNone(response["summary"])
        self.assertIn("tramadol", response["summary_withheld"])
        self.assertIn("MAJOR", response["facts"])          # database facts are unaffected

    def test_summary_naming_an_unchecked_brand_is_withheld(self):
        client = FakeClient("Warfarin with ibuprofen is risky; Prozac may be better.")
        self.assertIn("prozac", self.ask("warfarin and ibuprofen", client)["summary_withheld"])

    def test_summary_changing_the_severity_is_withheld(self):
        client = FakeClient("This is only a minor interaction.")
        response = self.ask("warfarin and ibuprofen", client)
        self.assertIsNone(response["summary"])
        self.assertIn("minor", response["summary_withheld"])

    def test_model_failure_never_blocks_the_database_answer(self):
        response = self.ask("warfarin and ibuprofen", FakeClient(error=OSError("connection refused")))
        self.assertIsNone(response["summary"])
        self.assertIn("model unavailable", response["summary_withheld"])
        self.assertEqual(response["found"], ["warfarin", "ibuprofen"])

    def test_model_is_not_asked_about_pairs_without_records(self):
        client = FakeClient("anything")
        response = self.ask("metformin and digoxin", client)
        self.assertEqual(client.prompts, [])
        self.assertIsNone(response["summary"])


class SummaryCheck(unittest.TestCase):
    TERMS = {"spironolactone": "spironolactone", "iron": "iron", "warfarin": "warfarin",
             "amphotericin b": "amphotericin b", "amphotericin b (liposomal)": "amphotericin b (liposomal)"}

    def test_a_short_name_inside_a_longer_word_is_not_a_mention(self):
        self.assertIsNone(check_summary("Spironolactone may interact.", "facts", ["spironolactone"], self.TERMS))

    def test_whole_word_mention_of_an_unchecked_drug_is_caught(self):
        self.assertIsNotNone(check_summary("Take iron later.", "facts", ["spironolactone"], self.TERMS))

    def test_part_of_an_allowed_name_is_not_a_different_drug(self):
        self.assertIsNone(check_summary("Amphotericin B (liposomal) may raise risk.", "facts",
                                        ["amphotericin b (liposomal)"], self.TERMS))

    def test_empty_and_overlong_outputs_are_withheld(self):
        self.assertIsNotNone(check_summary("  ", "facts", [], {}))
        self.assertIsNotNone(check_summary("One. Two. Three. Four.", "facts", [], {}))


if __name__ == "__main__":
    unittest.main()
