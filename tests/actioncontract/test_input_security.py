"""Allocation, JSON shape and error-path security regressions."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import actioncontract
ROOT = Path(actioncontract.__file__).resolve().parent
from actioncontract import (InputLimitError, MAX_DEPTH, MAX_INPUT_BYTES, MAX_ITEMS,
                            MAX_NODES, check_limits, decode, hash, load, read_bytes)
from actioncontract.acceptance import accept, markdown


class InputSecurityTests(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix="input-security-"))
        self.contract = ROOT / "contracts/synthetic.json"
        self.results = [ROOT / "samples" / (n + ".json") for n in ("sw", "ax", "ks")]

    def test_sparse_oversized_contract_and_each_checker(self):
        huge = self.work / "large.json"
        with huge.open("wb") as handle:
            handle.truncate(96 * 1024 * 1024)
        for index in range(4):
            paths = [self.contract, *self.results]
            paths[index] = huge
            with self.subTest(index=index):
                report = accept(paths[0], paths[1:])
                self.assertEqual(report["status"], "UNKNOWN")
                self.assertIn("INPUT_LIMIT_EXCEEDED", [f["code"] for f in report["findings"]])
                item = list(report["inputs"].values())[index]
                self.assertIsNone(item["sha256"])
                self.assertIn("1048576", markdown(report))
        for reader in (load, hash):
            with self.assertRaises(InputLimitError):
                reader(huge)

    def test_byte_boundary_and_growth_bounded_read(self):
        path = self.work / "boundary.json"
        for size in (MAX_INPUT_BYTES, MAX_INPUT_BYTES + 1):
            path.write_bytes(b" " * (size - 2) + b"{}")
            if size == MAX_INPUT_BYTES:
                self.assertEqual(decode(read_bytes(path)), {})
            else:
                with self.assertRaises(InputLimitError):
                    read_bytes(path)
        class Growing(io.BytesIO):
            def fileno(self):
                return 0
        import stat
        from types import SimpleNamespace
        path.write_bytes(b"{}")
        with patch("pathlib.Path.open", return_value=Growing(b"x" * (MAX_INPUT_BYTES + 50))), \
             patch("os.fstat", return_value=SimpleNamespace(st_mode=stat.S_IFREG, st_size=2)):
            with self.assertRaises(InputLimitError):
                read_bytes(path)

    def test_container_depth_and_total_node_boundaries(self):
        self.assertEqual(decode(json.dumps([0] * MAX_ITEMS).encode()), [0] * MAX_ITEMS)
        for value in ([0] * (MAX_ITEMS + 1), {str(i): 0 for i in range(MAX_ITEMS + 1)}):
            with self.assertRaises(InputLimitError):
                decode(json.dumps(value).encode())
        value = 0
        for _ in range(MAX_DEPTH):
            value = [value]
        check_limits(value)
        with self.assertRaises(InputLimitError):
            check_limits([value])
        # Every individual container is small, but their aggregate is bounded.
        with self.assertRaises(InputLimitError):
            check_limits([[0] * MAX_ITEMS for _ in range(MAX_NODES // MAX_ITEMS + 1)])

    def test_action_and_checker_count_limits(self):
        contract = load(self.contract)
        contract["x-tasks"] = [copy.deepcopy(contract["x-tasks"][0]) for _ in range(MAX_ITEMS + 1)]
        target = self.work / "contract.json"
        target.write_text(json.dumps(contract))
        self.assertEqual(accept(target, self.results)["status"], "UNKNOWN")
        target.write_text(json.dumps([{}] * (MAX_ITEMS + 1)))
        self.assertEqual(accept(self.contract, [self.results[0], target, self.results[2]])["status"], "UNKNOWN")
        with self.assertRaises(ValueError):
            accept(self.contract, self.results * 1000)
        with self.assertRaises(ValueError):
            accept(self.contract, self.results, expected_result_hashes=["0"] * 10000)

    def test_memory_error_during_read_decode_validate_and_check_is_unknown(self):
        for function in ("read_bytes", "decode", "validate", "_sw", "canonical"):
            with self.subTest(function=function), \
                 patch("actioncontract.acceptance." + function, side_effect=MemoryError):
                report = accept(self.contract, self.results)
                self.assertEqual(report["status"], "UNKNOWN")
                self.assertEqual(report["findings"][0]["code"], "INPUT_RESOURCE_LIMIT")
                self.assertIn("INPUT_RESOURCE_LIMIT", markdown(report))


if __name__ == "__main__":
    unittest.main()
