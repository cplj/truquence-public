"""Generated input properties; run with Hypothesis and TQ_PBT_SEED (default 20261015)."""
import csv
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from hypothesis import given, seed, settings, strategies as st
import actioncontract
from actioncontract import decode, InputLimitError, MAX_INPUT_BYTES
from actioncontract.acceptance import accept
from truquence.core import FIELDS, MAX_FILE_BYTES, parse_csv, reconcile

settings.register_profile("dx", max_examples=200, deadline=None, database=None)
settings.load_profile("dx")
SEED = int(os.environ.get("TQ_PBT_SEED", "20261015"))
ROOT = Path(actioncontract.__file__).resolve().parent
CONTRACT = ROOT / "contracts" / ("synthetic.json" if (ROOT / "contracts/synthetic.json").exists() else "stripe_synthetic.json")
RESULTS = [ROOT / "samples" / (n + ".json") for n in ("sw", "ax", "ks")]
scalar = st.none() | st.booleans() | st.integers() | st.text(max_size=30)
values = st.recursive(scalar, lambda children: st.lists(children, max_size=8) |
                      st.dictionaries(st.text(max_size=20), children, max_size=8), max_leaves=40)


class ParserProperties(unittest.TestCase):
    @seed(SEED)
    @given(values)
    def test_json_roundtrip(self, value):
        self.assertEqual(decode(json.dumps(value, ensure_ascii=True).encode()), value)

    @seed(SEED)
    @given(st.text(max_size=30), values, values)
    def test_duplicate_keys_rejected(self, key, first, second):
        raw = ('{' + json.dumps(key) + ':' + json.dumps(first) + ',' +
               json.dumps(key) + ':' + json.dumps(second) + '}').encode()
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            decode(raw)

    @seed(SEED)
    @given(st.integers(0, 3), st.binary(max_size=4096))
    def test_invalid_evidence_never_passes(self, index, tail):
        with tempfile.TemporaryDirectory(prefix="tq-pbt-") as work:
            invalid = Path(work) / "invalid.json"
            invalid.write_bytes(b'\xff' + tail)
            paths = [CONTRACT, *RESULTS]
            paths[index] = invalid
            report = accept(paths[0], paths[1:])
            self.assertEqual(report["status"], "UNKNOWN")
            self.assertEqual(report["counts"]["PASS"], 0)
            self.assertTrue(any(f["code"] == "INVALID_INPUT" for f in report["findings"]))

    @seed(SEED)
    @given(st.integers(1, 1024))
    def test_oversize_input_rejected_before_acceptance(self, extra):
        with self.assertRaises(InputLimitError):
            decode(b' ' * (MAX_INPUT_BYTES + extra))
        rows, problems, count = parse_csv(b' ' * (MAX_FILE_BYTES + extra), "usage")
        self.assertEqual((rows, count), ([], 0))
        self.assertEqual(problems[0]["code"], "EMPTY_OR_OVERSIZE_FILE")

    @seed(SEED)
    @given(st.binary(max_size=8192))
    def test_rejected_csv_never_ready(self, raw):
        rows, problems, count = parse_csv(raw, "usage")
        report = reconcile(raw, raw, True)
        if problems:
            self.assertEqual(report["state"], "Unknown")
            self.assertTrue(report["findings"])
        else:
            self.assertEqual(count, len(rows))

    @seed(SEED)
    @given(st.lists(st.tuples(st.text(alphabet='abc,\n"', max_size=19).map(lambda value: 'c' + value),
                              st.integers(0, 1000000)), min_size=1, max_size=20))
    def test_csv_writer_parser_roundtrip(self, entries):
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(FIELDS)
        for i, (customer, quantity) in enumerate(entries):
            writer.writerow(["event" + str(i), customer, "2026-10", "request", quantity])
        raw = output.getvalue().encode()
        rows, problems, count = parse_csv(raw, "usage")
        self.assertEqual(problems, [])
        self.assertEqual(count, len(entries))
        self.assertEqual([r["key"][0] for r in rows], [e[0] for e in entries])
        self.assertEqual([int(r["quantity"]) for r in rows], [e[1] for e in entries])
        self.assertEqual(reconcile(raw, raw, True)["state"], "Ready")


if __name__ == "__main__":
    unittest.main()
