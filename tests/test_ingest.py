import hashlib
import tempfile
import unittest
from pathlib import Path

from helpers import drug_id, memory_db, write_ddinter_csv

from medlite.ingest import ImportFormatError, load_ddinter_csv


class DDInterImport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = memory_db()

    def csv(self, rows, header=None, name="ddinter_downloads_code_A.csv"):
        path = Path(self.tmp.name) / name
        return write_ddinter_csv(path, rows, header) if header else write_ddinter_csv(path, rows)

    def test_import_records_provenance_and_normalizes_rows(self):
        path = self.csv([
            ["DDInter1", "Warfarin", "DDInter2", "Acetaminophen", "Moderate"],
            ["DDInter2", "Acetaminophen", "DDInter1", "Warfarin", "Moderate"],   # same unordered pair
            ["DDInter3", "Ibuprofen", "DDInter1", "Warfarin", "Major"],
            ["DDInter3", "Ibuprofen", "DDInter3", "Ibuprofen", "Minor"],         # self-pair is skipped
            ["DDInter4", "Fluorouracil", "DDInter1", "Warfarin", "Unknown"],
        ])
        result = load_ddinter_csv(self.db, path, release="test-release")
        self.assertEqual(result.rows, 5)
        self.assertEqual(result.sha256, hashlib.sha256(path.read_bytes()).hexdigest())

        source = self.db.execute("SELECT name, release, source_file, sha256 FROM data_source").fetchall()
        self.assertEqual(source, [("DDInter", "test-release", path.name, result.sha256)])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM interaction").fetchone()[0], 3)
        severity = dict(self.db.execute(
            "SELECT d.name, i.severity FROM interaction i JOIN drug d ON d.id = i.a OR d.id = i.b "
            "WHERE d.name != 'warfarin'"))
        self.assertEqual(severity, {"acetaminophen": "moderate", "ibuprofen": "major", "fluorouracil": "unknown"})
        record = self.db.execute("SELECT source_record_id FROM interaction WHERE ? IN (a, b) AND ? IN (a, b)",
                                 (drug_id(self.db, "ibuprofen"), drug_id(self.db, "warfarin"))).fetchone()[0]
        self.assertEqual(record, "DDInter3|DDInter1")

    def test_brand_aliases_attach_to_generics_present_in_the_data(self):
        load_ddinter_csv(self.db, self.csv([["1", "Acetaminophen", "2", "Warfarin", "Moderate"]]))
        alias = dict(self.db.execute("SELECT alias, drug_id FROM alias"))
        self.assertEqual(alias["crocin"], drug_id(self.db, "acetaminophen"))
        self.assertEqual(alias["coumadin"], drug_id(self.db, "warfarin"))

    def test_wrong_headers_are_rejected_before_anything_is_written(self):
        path = self.csv([["a", "b"]], header=["Name", "Other"])
        with self.assertRaises(ImportFormatError):
            load_ddinter_csv(self.db, path)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM data_source").fetchone()[0], 0)

    def test_reimporting_the_same_file_is_idempotent(self):
        path = self.csv([["1", "Warfarin", "2", "Ibuprofen", "Major"]])
        load_ddinter_csv(self.db, path, release="r")
        load_ddinter_csv(self.db, path, release="r")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM data_source").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM interaction").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
