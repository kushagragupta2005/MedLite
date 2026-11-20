import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from helpers import ROOT, write_ddinter_csv

from medlite.config import Settings
from medlite.db import connect
from medlite.demo import load_demo
from medlite.server import MAX_BODY_BYTES, make_server


def run_cli(*args, db, entry=("-m", "medlite")):
    env = dict(os.environ, MEDLITE_DB=str(db), PYTHONPATH=str(ROOT))
    return subprocess.run([sys.executable, *entry, *args], capture_output=True, text=True, env=env, cwd=ROOT)


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        db_path = Path(cls.tmp.name) / "med.db"
        db = connect(db_path)
        load_demo(db)
        db.close()
        cls.server = make_server(Settings(db_path=str(db_path)), port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, response.getheader("Content-Type"), data

    def test_page(self):
        status, content_type, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertTrue(content_type.startswith("text/html"))
        self.assertIn(b"MedLite", body)

    def test_unknown_paths_are_404(self):
        self.assertEqual(self.request("GET", "/admin")[0], 404)
        self.assertEqual(self.request("POST", "/other", b"{}")[0], 404)

    def test_ask(self):
        status, _, body = self.request("POST", "/ask", json.dumps({"q": "warfarin and ibuprofen"}).encode(),
                                       {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["found"], ["warfarin", "ibuprofen"])

    def test_malformed_json_is_a_400_not_a_dropped_connection(self):
        for body in (b"{not json", b"[1, 2]", b"\xff\xfe"):
            status, _, data = self.request("POST", "/ask", body)
            self.assertEqual(status, 400, body)
            self.assertIn("error", json.loads(data))

    def test_oversized_body_is_rejected(self):
        status, _, _ = self.request("POST", "/ask", b" " * (MAX_BODY_BYTES + 1))
        self.assertEqual(status, 413)


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "med.db"

    def test_init_then_ask(self):
        self.assertEqual(run_cli("init", db=self.db).returncode, 0)
        result = run_cli("ask", "coumadin", "and", "advil", "--exact", db=self.db)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Recognised: warfarin, ibuprofen", result.stdout)
        self.assertIn("MAJOR", result.stdout)

    def test_legacy_entry_point_still_works(self):
        run_cli("init", db=self.db)
        result = run_cli("ask", "warfarin", db=self.db, entry=(str(ROOT / "baseline" / "med.py"),))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("warfarin has 3 listed interactions", result.stdout)

    def test_load_with_release_label_and_stats(self):
        csv_path = write_ddinter_csv(Path(self.tmp.name) / "ddinter_downloads_code_A.csv",
                                     [["DDInter1", "Warfarin", "DDInter2", "Ibuprofen", "Major"]])
        result = run_cli("load", str(csv_path), "--release", "local-test", db=self.db)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Imported 1 rows (2 drugs)", result.stdout)
        stats = run_cli("stats", db=self.db)
        self.assertIn("source: DDInter local-test / ddinter_downloads_code_A.csv", stats.stdout)

    def test_load_rejects_a_non_ddinter_csv(self):
        csv_path = write_ddinter_csv(Path(self.tmp.name) / "bad.csv", [["x"]], header=["Name"])
        result = run_cli("load", str(csv_path), db=self.db)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Could not find drug A/B columns", result.stderr)


if __name__ == "__main__":
    unittest.main()
