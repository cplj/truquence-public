import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import actioncontract
ROOT = Path(actioncontract.__file__).resolve().parent
from actioncontract import decode, hash, load, validate
from actioncontract.acceptance import accept, canonical, markdown


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.contract = ROOT / "contracts/synthetic.json"
        self.paths = []
        for name in ("sw", "ax", "ks"):
            target = self.work / (name + ".json")
            target.write_bytes((ROOT / "samples" / target.name).read_bytes())
            self.paths.append(target)

    def change(self, index, mutate):
        path = self.paths[index]
        value = decode(path.read_bytes())
        mutate(value)
        path.write_text(json.dumps(value), encoding="utf-8")

    def report(self, **kwargs):
        return accept(self.contract, self.paths, **kwargs)

    def test_normal_load_validate_hash_and_three_passes(self):
        contract = load(self.contract)
        self.assertIs(validate(contract), contract)
        self.assertEqual(hash(self.contract), hashlib.sha256(self.contract.read_bytes()).hexdigest())
        report = self.report()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["state"], "Ready")
        self.assertEqual(report["counts"], {"PASS": 3, "FAIL": 0, "UNKNOWN": 0})
        self.assertEqual([a["id"] for a in report["actions"]], ["refund", "create_customer", "send_receipt"])
        for name, path in zip(("signwarden", "axiocairn", "kinesift"), self.paths):
            self.assertEqual(report["inputs"][name]["sha256"], hash(path))
        rendered = markdown(report)
        self.assertIn("one-page", rendered)
        self.assertIn("unsigned", rendered)
        self.assertIn(hash(self.contract), rendered)

    def test_missing_every_required_contract_field(self):
        contract = load(self.contract)
        for key in contract:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate({k: v for k, v in contract.items() if k != key})
        for key in contract["x-tasks"][0]:
            mutated = copy.deepcopy(contract)
            del mutated["x-tasks"][0][key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(mutated)

    def test_no_unsourced_contract_fields(self):
        contract = load(self.contract)
        contract["x-tasks"][0]["x-price"] = 100
        with self.assertRaises(ValueError):
            validate(contract)

    def test_hint_types_and_missing_prefix(self):
        for key, value in [("idempotentHint", "true"), ("tool", "refund"), ("x-expect_total_effects", True)]:
            contract = load(self.contract)
            contract["x-tasks"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(contract)

    def test_duplicate_contract_id(self):
        contract = load(self.contract)
        contract["x-tasks"][1]["x-id"] = "refund"
        with self.assertRaises(ValueError):
            validate(contract)

    def test_action_outside_declared_scope_is_invalid(self):
        for key in ("x-scope", "x-allowed_actions"):
            contract = load(self.contract)
            contract["x-tasks"][0][key] = ["other_tool"]
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(contract)

    def test_empty_contract_and_malformed_scope(self):
        for value in ([], [{"bad": True}]):
            contract = load(self.contract)
            if value:
                contract["x-tasks"][0]["x-scope"] = value
            else:
                contract["x-tasks"] = value
            with self.assertRaises(ValueError):
                validate(contract)

    def test_unknown_recovery_never_passes(self):
        self.change(1, lambda rows: rows[2].update(state="UNKNOWN", detail="receipt query unavailable; no retry"))
        report = self.report()
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertEqual(report["actions"][2]["status"], "UNKNOWN")
        self.assertEqual(report["counts"]["PASS"], 2)
        self.assertIn("do not retry", markdown(report))

    def test_all_incomplete_recovery_states_are_unknown(self):
        for state in ("PREPARED", "IN_FLIGHT", "RETRY_SAFE", "MANUAL_REVIEW", "UNRECOGNIZED"):
            self.change(1, lambda rows: rows[0].update(state=state))
            with self.subTest(state=state):
                self.assertEqual(self.report()["actions"][0]["status"], "UNKNOWN")

    def test_missing_result_is_unknown(self):
        self.change(2, lambda rows: rows.pop())
        self.assertEqual(self.report()["actions"][2]["status"], "UNKNOWN")

    def test_missing_oracle_field_is_unknown(self):
        self.change(2, lambda rows: rows[0]["verification"].pop("forbidden_attempts"))
        self.assertEqual(self.report()["actions"][0]["status"], "UNKNOWN")

    def test_missing_recovery_field_is_unknown(self):
        self.change(1, lambda rows: rows[0].pop("payload"))
        self.assertEqual(self.report()["actions"][0]["status"], "UNKNOWN")

    def test_unknown_oracle_is_unknown(self):
        self.change(2, lambda rows: rows[0].update(status="UNKNOWN", accepted=None))
        self.assertEqual(self.report()["status"], "UNKNOWN")

    def test_forbidden_attempt_blocks(self):
        def mutate(rows):
            rows[0].update(status="FAILED", accepted=False)
            rows[0]["verification"].update(forbidden_attempts=1, accepted=False)
        self.change(2, mutate)
        self.assertEqual(self.report()["actions"][0]["status"], "FAIL")

    def test_forged_success_contradicts_oracle(self):
        self.change(2, lambda rows: rows[0]["verification"].update(forbidden_mutations=["payments"]))
        self.assertEqual(self.report()["status"], "FAIL")

    def test_authorization_fail_and_unknown_precedence(self):
        self.change(0, lambda doc: doc["cases"][0].update(result="FAIL"))
        self.change(1, lambda rows: rows[0].update(state="UNKNOWN"))
        self.assertEqual(self.report()["actions"][0]["status"], "FAIL")

    def test_authorization_incomplete_steps(self):
        self.change(0, lambda doc: doc["cases"][0].update(not_executed_steps=[1]))
        self.assertEqual(self.report()["status"], "UNKNOWN")

    def test_authorization_missing_check_details(self):
        self.change(0, lambda doc: doc["cases"][0]["checks"][0].pop("observed"))
        self.assertEqual(self.report()["status"], "UNKNOWN")

    def test_authorization_false_pass(self):
        self.change(0, lambda doc: doc["cases"][0]["checks"][0]["observed"].update(status="denied"))
        self.assertEqual(self.report()["status"], "FAIL")

    def test_wrong_payload_tool_account_and_version_fail(self):
        original = self.paths[1].read_bytes()
        for fields in ({"payload": "{}"}, {"tool": '["refund","ledger","other-account"]'}, {"version": "v9"}):
            self.paths[1].write_bytes(original)
            self.change(1, lambda rows: rows[0].update(fields))
            with self.subTest(fields=fields):
                self.assertEqual(self.report()["actions"][0]["status"], "FAIL")

    def test_extra_effect_fails(self):
        self.change(0, lambda doc: doc["cases"][0]["ledger"].append({"tool": "send_receipt"}))
        self.assertEqual(self.report()["status"], "FAIL")

    def test_cross_checker_effect_counts_block_acceptance(self):
        for index in (0, 2):  # ledger and append actions both report one recovered effect
            for count in (0, 2):
                with self.subTest(index=index, count=count):
                    contract = load(ROOT / "contracts/synthetic.json")
                    contract["x-tasks"][index]["x-expect_total_effects"] = count
                    self.contract = self.work / "contract.json"
                    self.contract.write_text(json.dumps(contract), encoding="utf-8")
                    sw = decode((ROOT / "samples/sw.json").read_bytes())
                    row = sw["cases"][index]
                    row["ledger"] *= count
                    row["checks"] = [{"op": "total_effects", "expected": count,
                                      "observed": count, "result": "PASS"}]
                    self.paths[0].write_text(json.dumps(sw), encoding="utf-8")
                    report = self.report()
                    self.assertEqual(report["status"], "FAIL")
                    self.assertEqual(report["counts"], {"PASS": 2, "FAIL": 1, "UNKNOWN": 0})
                    reason = report["actions"][index]["checks"]["axiocairn"]["reason"]
                    for detail in ("Effect-count contradiction", "x-expect_total_effects=" + str(count),
                                   "SignWarden ledger=" + str(count), "Axiocairn COMPLETED=1"):
                        self.assertIn(detail, reason)
                        self.assertIn(detail, markdown(report))

    def test_recovery_and_ledger_count_conflict_is_explicit(self):
        self.change(0, lambda doc: doc["cases"][0].update(ledger=[]))
        report = self.report()
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("SignWarden ledger=0", markdown(report))
        self.assertIn("Axiocairn COMPLETED=1", markdown(report))

    def test_unknown_recovery_does_not_imply_one_effect(self):
        contract = load(self.contract)
        contract["x-tasks"][0]["x-expect_total_effects"] = 0
        self.contract = self.work / "contract.json"
        self.contract.write_text(json.dumps(contract), encoding="utf-8")
        def mutate(doc):
            row = doc["cases"][0]
            row["ledger"] = []
            row["checks"] = [{"op": "total_effects", "expected": 0, "observed": 0, "result": "PASS"}]
        self.change(0, mutate)
        self.change(1, lambda rows: rows[0].update(state="UNKNOWN"))
        self.assertEqual(self.report()["status"], "UNKNOWN")

    def test_recovery_numeric_payload_conflict_is_not_normalized_away(self):
        def mutate(rows):
            payload = json.loads(rows[0]["payload"])
            payload["amount"] = 50.0
            rows[0]["payload"] = json.dumps(payload)
        self.change(1, mutate)
        self.assertEqual(self.report()["status"], "FAIL")

    def test_duplicate_and_unmapped_ids_never_pass(self):
        original = self.paths[1].read_bytes()
        for action_id in ("refund", "unmapped"):
            self.paths[1].write_bytes(original)
            self.change(1, lambda rows: rows[1].update(id=action_id))
            with self.subTest(action_id=action_id):
                self.assertEqual(self.report()["status"], "UNKNOWN")

    def test_contract_hash_mismatch_fails_every_action(self):
        report = self.report(expected_contract_hash="0" * 64)
        self.assertEqual(report["counts"]["FAIL"], 3)
        self.assertIn("HASH_MISMATCH", [f["code"] for f in report["findings"]])

    def test_result_hash_mismatch_for_each_checker(self):
        for index in range(3):
            pins = [hash(p) for p in self.paths]
            pins[index] = "0" * 64
            with self.subTest(index=index):
                self.assertEqual(self.report(expected_result_hashes=pins)["counts"]["FAIL"], 3)

    def test_exact_hash_pins_pass_and_whitespace_change_fails(self):
        pins = [hash(p) for p in self.paths]
        self.assertEqual(self.report(expected_contract_hash=hash(self.contract), expected_result_hashes=pins)["status"], "PASS")
        self.paths[0].write_bytes(self.paths[0].read_bytes() + b"\n")
        self.assertEqual(self.report(expected_result_hashes=pins)["status"], "FAIL")

    def test_native_report_hash_mismatch(self):
        self.change(0, lambda doc: doc.update(report_sha256="0" * 64))
        self.assertEqual(self.report()["status"], "FAIL")

    def test_native_report_hash_matches(self):
        self.change(0, lambda doc: doc.update(report_sha256=hashlib.sha256(canonical(doc)).hexdigest()))
        self.assertEqual(self.report()["status"], "PASS")

    def test_invalid_contract_is_reported(self):
        path = self.work / "contract.json"
        path.write_text('{}')
        report = accept(path, self.paths)
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertEqual(report["actions"], [])
        self.assertEqual([f["code"] for f in report["findings"]], ["INVALID_CONTRACT"])
        rendered = markdown(report)
        self.assertIn("Invalid contract; no actions could be evaluated", rendered)
        self.assertIn("| — | Invalid contract | Not evaluated | Not evaluated | Not evaluated |", rendered)
        self.assertNotIn("0 unresolved", rendered)
        self.assertIn(report["findings"][0]["detail"], rendered)

    def test_unreadable_malformed_duplicate_and_nonfinite_inputs(self):
        for raw in (b'{', b'{"a":1,"a":2}', b'{"a":NaN}', b'\xff'):
            self.paths[0].write_bytes(raw)
            with self.subTest(raw=raw):
                report = self.report()
                self.assertEqual(report["status"], "UNKNOWN")
                self.assertEqual(report["inputs"]["signwarden"]["sha256"], hash(self.paths[0]))
        self.paths[0].rename(self.work / "moved.json")
        self.assertEqual(self.report()["status"], "UNKNOWN")

    def cli(self, *extra):
        return subprocess.run([sys.executable, "-m", "actioncontract", "accept", "--contract", str(self.contract),
                               "--results", *map(str, self.paths), "--out", str(self.work / "report"), *extra],
                              text=True, capture_output=True, cwd=self.work)

    def test_cli_creates_two_reports_and_does_not_overwrite(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "PASS")
        path = self.work / "report.json"
        original = path.read_bytes()
        self.assertTrue((self.work / "report.md").is_file())
        again = self.cli()
        self.assertEqual(again.returncode, 3)
        self.assertEqual(path.read_bytes(), original)

    def test_cli_unknown_and_hash_mismatch_exit_codes(self):
        self.change(1, lambda rows: rows[2].update(state="UNKNOWN"))
        result = self.cli()
        self.assertEqual(result.returncode, 2, result.stderr)
        result = self.cli("--out", str(self.work / "failure"), "--expect-contract-hash", "0" * 64)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "FAIL")

    def test_cli_cross_checker_contradiction_fails(self):
        contract = load(self.contract)
        contract["x-tasks"][0]["x-expect_total_effects"] = 2
        self.contract = self.work / "contract.json"
        self.contract.write_text(json.dumps(contract), encoding="utf-8")
        def mutate(doc):
            row = doc["cases"][0]
            row["ledger"] *= 2
            row["checks"] = [{"op": "total_effects", "expected": 2, "observed": 2, "result": "PASS"}]
        self.change(0, mutate)
        result = self.cli()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "FAIL")
        self.assertIn("Effect-count contradiction", (self.work / "report.md").read_text())

    def test_cli_invalid_contract_explains_missing_fields(self):
        for key, index in (("x-actor", 0), ("x-data_mode", None)):
            with self.subTest(key=key):
                contract = load(ROOT / "contracts/synthetic.json")
                del (contract if index is None else contract["x-tasks"][index])[key]
                self.contract = self.work / "contract.json"
                self.contract.write_text(json.dumps(contract), encoding="utf-8")
                prefix = self.work / key
                result = self.cli("--out", str(prefix))
                self.assertEqual(result.returncode, 2, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual([f["code"] for f in report["findings"]], ["INVALID_CONTRACT"])
                rendered = prefix.with_suffix(".md").read_text()
                self.assertIn("Invalid contract; no actions could be evaluated", rendered)
                self.assertIn("| — | Invalid contract | Not evaluated | Not evaluated | Not evaluated |", rendered)
                self.assertIn("missing " + key, rendered)
                self.assertNotIn("INVALID_RESULTS", rendered)


if __name__ == "__main__":
    unittest.main()
