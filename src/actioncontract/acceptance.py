"""Merge native synthetic results; no checker execution or external side effects."""
import hashlib
import json

from . import InputLimitError, decode, read_bytes, validate

NAMES = ("signwarden", "axiocairn", "kinesift")
STATES = {"PASS": "Ready", "FAIL": "Failed", "UNKNOWN": "Unknown"}


def combine(statuses):
    return "FAIL" if "FAIL" in statuses else "UNKNOWN" if not statuses or "UNKNOWN" in statuses else "PASS"


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def fingerprint(raw):
    return hashlib.sha256(raw).hexdigest()


def _index(value, key, expected):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("expected a list of native results")
    ids = [row.get(key) for row in value]
    if any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("missing or duplicate result ID")
    if set(ids) - set(expected):
        raise ValueError("unmapped result ID")
    return dict(zip(ids, value))


def _sw(row, action):
    status = row.get("result")
    checks = row.get("checks")
    if status == "FAIL":
        return "FAIL", "Authorization checker reported failure."
    if not isinstance(checks, list) or not checks or any(not isinstance(c, dict) for c in checks):
        return "UNKNOWN", "Authorization checks are missing."
    if any(c.get("result") == "FAIL" for c in checks):
        return "FAIL", "Authorization check failed."
    if (status != "PASS" or any(c.get("result") != "PASS" for c in checks)
            or row.get("not_executed_steps") != [] or "stopped_reason" not in row
            or row["stopped_reason"] is not None):
        return "UNKNOWN", "Authorization evidence is incomplete or interrupted."
    for check in checks:
        if "expected" not in check or "observed" not in check:
            return "UNKNOWN", "Authorization expected/observed evidence is missing."
        expected, observed = check["expected"], check["observed"]
        if isinstance(expected, dict):
            if not isinstance(observed, dict) or not expected or set(expected) - {"status", "effects"}:
                return "UNKNOWN", "Authorization evidence has an unsupported shape."
            if "status" in expected and (observed.get("status") not in {"executed", "denied", "pending_approval", "error", "unknown"}):
                return "UNKNOWN", "Authorization checker returned no valid native status."
            if "status" in expected and (not isinstance(expected["status"], list) or observed.get("status") not in expected["status"]):
                return "FAIL", "Authorization status contradicts the expected result."
            if "effects" in expected and canonical(expected["effects"]) != canonical(observed.get("effects")):
                return "FAIL", "Authorization effects contradict the expected result."
        elif check.get("op") != "total_effects" or type(expected) is not int or expected != observed:
            return "FAIL", "Authorization effect count contradicts the expected result."
    ledger = row.get("ledger")
    if not isinstance(ledger, list):
        return "UNKNOWN", "Side-effect ledger is missing."
    expected = {"tool": action["x-tool"], "tenant": action["x-tenant"], "args": action["x-payload"]}
    if len(ledger) != action["x-expect_total_effects"] or any(canonical(effect) != canonical(expected) for effect in ledger):
        return "FAIL", "Authorization ledger differs from the agreed action or effect count."
    return "PASS", "Authorization cases passed for this synthetic action."


def _ax(row, action):
    if not all(isinstance(row.get(k), str) for k in ("id", "tool", "payload", "version", "state", "detail")):
        return "UNKNOWN", "Recovery record is incomplete."
    tool = decode(row["tool"].encode("utf-8"))
    payload = decode(row["payload"].encode("utf-8"))
    if (tool != [action["x-tool"], action["x-kind"], action["x-account"]]
            or canonical(payload) != canonical(action["x-payload"]) or row["version"] != action["x-version"]):
        return "FAIL", "Recovery identity, payload or version differs from the contract."
    if row["state"] == "COMPLETED":
        return "PASS", "Recovery checker reported one matching effect."
    if row["state"] == "VERSION_MISMATCH":
        return "FAIL", "Recovery checker reported a version mismatch."
    return "UNKNOWN", "Completion is unresolved; do not retry on this report."


def _ks(row, action):
    if row.get("schema") != "kinesift.run.v1" or row.get("data_mode") != "SYNTHETIC":
        return "UNKNOWN", "Unsupported completion result format."
    if row.get("status") not in {"SUCCEEDED", "FAILED"}:
        return "UNKNOWN", "Completion oracle is unavailable or interrupted."
    verification = row.get("verification")
    if (not isinstance(verification, dict)
            or type(verification.get("task_state_exact")) is not bool
            or not isinstance(verification.get("forbidden_mutations"), list)
            or type(verification.get("forbidden_attempts")) is not int
            or verification["forbidden_attempts"] < 0
            or type(verification.get("accepted")) is not bool
            or type(row.get("accepted")) is not bool):
        return "UNKNOWN", "Completion or forbidden-side-effect evidence is missing."
    accepted = (verification["task_state_exact"] and not verification["forbidden_mutations"]
                and verification["forbidden_attempts"] == 0)
    if row["accepted"] != accepted or verification["accepted"] != accepted or (row["status"] == "SUCCEEDED") != accepted:
        return "FAIL", "Completion result contradicts its oracle evidence."
    return ("PASS", "Exact final state and zero forbidden changes or attempts reported.") if accepted else (
        "FAIL", "Completion or forbidden-side-effect oracle failed.")


def _accept(contract_path, result_paths, expected_contract_hash=None, expected_result_hashes=None):
    """Hash once-read input bytes. Optional independent pins detect changed files."""
    if len(result_paths) != 3:
        raise ValueError("provide SignWarden, Axiocairn, Kinesift files in that order")
    if expected_result_hashes is not None and len(expected_result_hashes) != 3:
        raise ValueError("three expected result hashes required")
    inputs, documents, findings = {}, {}, []
    for name, path in zip(("contract",) + NAMES, [contract_path, *result_paths]):
        try:
            raw = read_bytes(path)
            inputs[name] = {"path": str(path), "sha256": fingerprint(raw), "bytes": len(raw),
                            "hash_scope": "exact_provided_bytes"}
            documents[name] = decode(raw)
        except (OSError, ValueError, RecursionError) as error:
            inputs.setdefault(name, {"path": str(path), "sha256": None, "bytes": None})
            findings.append({"code": "INPUT_LIMIT_EXCEEDED" if isinstance(error, InputLimitError) else "INVALID_INPUT", "severity": "unknown", "input": name,
                             "detail": str(error), "next_action": "Supply a readable native JSON result or valid v0 contract."})
    pins = dict(zip(NAMES, expected_result_hashes)) if expected_result_hashes is not None else {}
    if expected_contract_hash is not None:
        pins["contract"] = expected_contract_hash
    for name, pin in pins.items():
        if inputs[name]["sha256"] != pin:
            findings.append({"code": "HASH_MISMATCH", "severity": "error", "input": name,
                             "expected": pin, "observed": inputs[name]["sha256"],
                             "next_action": "Stop acceptance and reconcile with the independently supplied hash."})
    contract = documents.get("contract")
    contract_valid = True
    try:
        validate(contract)
    except (ValueError, TypeError, RecursionError) as error:
        findings.append({"code": "INVALID_CONTRACT", "severity": "unknown", "detail": str(error),
                         "next_action": "Correct the contract and obtain fresh checker results."})
        contract = {"x-tasks": []}
        contract_valid = False
    ids = [action["x-id"] for action in contract["x-tasks"]]
    indexed = {}
    for name, key in zip(NAMES if contract_valid else (), ("id", "id", "task")):
        try:
            doc = documents.get(name)
            if name == "signwarden":
                if not isinstance(doc, dict) or doc.get("schema") not in {"signwarden.report.v0", "signwarden.report.v1"}:
                    raise ValueError("unsupported authorization report")
                if "report_sha256" in doc and fingerprint(canonical({k: v for k, v in doc.items() if k != "report_sha256"})) != doc["report_sha256"]:
                    findings.append({"code": "HASH_MISMATCH", "severity": "error", "input": name,
                                     "next_action": "Reconcile the native report fingerprint."})
                doc = doc.get("cases")
            elif isinstance(doc, dict):
                doc = [doc]
            indexed[name] = _index(doc, key, ids)
        except (ValueError, TypeError) as error:
            indexed[name] = {}
            findings.append({"code": "INVALID_RESULTS", "severity": "unknown", "input": name,
                             "detail": str(error), "next_action": "Provide unique native results for every contract action ID."})
    actions = []
    for action in contract["x-tasks"]:
        checks = {}
        for name, checker in zip(NAMES, (_sw, _ax, _ks)):
            row = indexed[name].get(action["x-id"])
            try:
                status, reason = checker(row, action) if row is not None else ("UNKNOWN", "No result for this action ID.")
            except (ValueError, TypeError, KeyError, RecursionError):
                status, reason = "UNKNOWN", "Malformed native result evidence."
            checks[name] = {"status": status, "reason": reason}
        sw_row = indexed["signwarden"].get(action["x-id"])
        ledger = sw_row.get("ledger") if sw_row is not None else None
        if checks["axiocairn"]["status"] == "PASS" and (
                action["x-expect_total_effects"] != 1 or isinstance(ledger, list) and len(ledger) != 1):
            checks["axiocairn"] = {
                "status": "FAIL",
                "reason": "Effect-count contradiction: contract x-expect_total_effects="
                          + str(action["x-expect_total_effects"]) + "; SignWarden ledger="
                          + (str(len(ledger)) if isinstance(ledger, list) else "unavailable")
                          + "; Axiocairn COMPLETED=1."}
        local = [v["status"] for v in checks.values()]
        local.extend("FAIL" if f["severity"] == "error" else "UNKNOWN" for f in findings)
        actions.append({"id": action["x-id"], "status": combine(local), "checks": checks})
    status = combine([a["status"] for a in actions] + ["FAIL" if f["severity"] == "error" else "UNKNOWN" for f in findings])
    return {"policy_version": "action-contract-v0", "state": STATES[status], "status": status,
            "scope": "Synthetic supplied evidence only; unsigned, no customer or production acceptance. Native checker-to-contract binding awaits step 1b.",
            "data_mode": "SYNTHETIC", "inputs": inputs,
            "counts": {s: sum(a["status"] == s for a in actions) for s in STATES},
            "findings": findings, "actions": actions}


def accept(contract_path, result_paths, expected_contract_hash=None, expected_result_hashes=None):
    try:
        return _accept(contract_path, result_paths, expected_contract_hash, expected_result_hashes)
    except MemoryError:
        return {"policy_version": "action-contract-v0", "state": "Unknown", "status": "UNKNOWN",
                "scope": "Input resource limit; no acceptance evaluated.", "data_mode": "SYNTHETIC",
                "inputs": {}, "counts": {s: 0 for s in STATES}, "actions": [],
                "findings": [{"code": "INPUT_RESOURCE_LIMIT", "severity": "unknown",
                              "detail": "Insufficient memory to process bounded input.",
                              "next_action": "Reduce input size and reconcile before rerunning."}]}


def markdown(report):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ").replace("`", "'")
    counts = report["counts"]
    invalid_contract = any(f["code"] == "INVALID_CONTRACT" for f in report["findings"])
    summary = ("Invalid contract; no actions could be evaluated." if invalid_contract else
               str(counts["PASS"]) + " passed; " + str(counts["FAIL"]) + " failed; "
               + str(counts["UNKNOWN"]) + " unresolved.")
    lines = ["# Action acceptance — one-page summary", "",
             "Decision: **" + report["status"] + "**. " + summary, "",
             "PASS means the supplied synthetic checks agree. FAIL blocks acceptance. UNKNOWN blocks acceptance until missing evidence is resolved. A lost acknowledgement never permits an automatic retry.", "",
             report["scope"], "", "| Action | Decision | Authorization | Recovery | Completion |",
             "|---|---|---|---|---|"]
    if invalid_contract:
        lines.append("| — | Invalid contract | Not evaluated | Not evaluated | Not evaluated |")
    for action in report["actions"]:
        lines.append("| " + " | ".join([cell(action["id"]), action["status"],
                     *[action["checks"][n]["status"] for n in NAMES]]) + " |")
        for name, check in action["checks"].items():
            if check["status"] != "PASS":
                lines.append("")
                lines.append(cell(action["id"]) + " / " + name + ": " + cell(check["reason"]))
    next_step = ("Next step: correct the invalid contract before mapping or evaluating checker results."
                 if invalid_contract else
                 "Next step: review failures or obtain missing checker evidence; rerun against the same agreed contract. Passing synthetic samples still need independent QA and an authorized acceptance owner.")
    lines.extend(["", next_step, "", "Exact-byte SHA-256 fingerprints (integrity only; no signer identity):", ""])
    for name, item in report["inputs"].items():
        lines.append("- " + name + ": `" + str(item["sha256"]) + "`")
    for finding in report["findings"]:
        detail = cell(finding["detail"]) + ". " if "detail" in finding else ""
        lines.append("- " + finding["code"] + ": " + detail + cell(finding["next_action"]))
    return "\n".join(lines) + "\n"
