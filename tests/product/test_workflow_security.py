"""Workflow JSON uses the same bounded input policy as native evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from actioncontract import MAX_INPUT_BYTES, MAX_ITEMS
from truquence.workflow import accept, read


class WorkflowInputSecurityTests(unittest.TestCase):
    def test_oversized_contract_and_execution_fail_closed(self):
        work = Path(tempfile.mkdtemp(prefix="workflow-security-"))
        small, huge = work / "small.json", work / "huge.json"
        small.write_text("{}")
        with huge.open("wb") as handle:
            handle.truncate(96 * 1024 * 1024)
        for contract, execution in ((huge, small), (small, huge)):
            report = accept(contract, execution, "n8n")
            self.assertEqual(report["status"], "UNKNOWN")
            self.assertIn("INPUT_LIMIT_EXCEEDED", report["checks"][0]["reason"])
        huge.write_text(json.dumps([0] * (MAX_ITEMS + 1)))
        self.assertEqual(accept(small, huge, "n8n")["status"], "UNKNOWN")

    def test_memory_error_is_explicit_unknown(self):
        with patch("truquence.workflow.read", side_effect=MemoryError):
            report = accept("contract.json", "execution.json", "n8n")
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertIn("INPUT_RESOURCE_LIMIT", report["checks"][0]["reason"])

    def test_read_exact_byte_limit(self):
        path = Path(tempfile.mkdtemp(prefix="workflow-boundary-")) / "input.json"
        path.write_bytes(b" " * (MAX_INPUT_BYTES - 2) + b"{}")
        value, meta = read(path)
        self.assertEqual(value, {})
        self.assertEqual(meta["bytes"], MAX_INPUT_BYTES)


if __name__ == "__main__":
    unittest.main()
