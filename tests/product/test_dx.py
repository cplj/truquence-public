"""DX contracts for command discovery and readable input failures."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from truquence.entry import main


class DXTests(unittest.TestCase):
    def test_top_help_discovers_accept_and_csv(self):
        for args, exit_code in ((["--help"], 0), ([], 2)):
            with patch("sys.argv", ["truquence", *args]), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(), exit_code)
            self.assertIn("accept --contract", output.getvalue())
            self.assertIn("USAGE.csv BILLED.csv", output.getvalue())

    def test_accept_help_maps_roles(self):
        with patch("sys.argv", ["truquence", "accept", "--help"]), contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as exit_status:
                main()
        self.assertEqual(exit_status.exception.code, 0)
        for text in ("AUTHORIZATION", "RECOVERY", "COMPLETION", "signwarden", "axiocairn", "kinesift"):
            self.assertIn(text, output.getvalue())

    def test_missing_csv_names_input_and_recovery(self):
        with tempfile.TemporaryDirectory(prefix="tq-dx-") as work:
            existing = Path(work) / "usage.csv"
            existing.write_text("event_id,customer_id,period,unit,quantity\n")
            missing = Path(work) / "missing.csv"
            for usage, billed in ((missing, existing), (existing, missing)):
                with patch("sys.argv", ["truquence", str(usage), str(billed), "--out", str(Path(work) / "out.json")]), contextlib.redirect_stderr(io.StringIO()) as output:
                    self.assertEqual(main(), 2)
                error = json.loads(output.getvalue())
                self.assertEqual(error["path"], str(missing))
                self.assertEqual(error["error"], "FileNotFoundError")
                self.assertIn("Correct the input", error["next_action"])
                self.assertIn("missing.csv", error["detail"])
