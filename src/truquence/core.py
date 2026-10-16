"""Compare provided atomic event rows, not money, source completeness or API state."""
import csv
import hashlib
import io
import re
from collections import defaultdict
from decimal import Decimal

POLICY_VERSION = "usage-events-1.0.0"
FIELDS = ["event_id", "customer_id", "period", "unit", "quantity"]
UNITS = {"request", "token", "second"}
MAX_FILE_BYTES = 524288
MAX_ROWS = 10000
MAX_QUANTITY = Decimal("1000000000000")
csv.field_size_limit(4096)


ACTIONS = {
    "DUPLICATE_SOURCE_EVENT": "Inspect the source rows sharing this key; establish which event record is authoritative before producing a corrected file.",
    "DUPLICATE_BILLED_EVENT": "Inspect billed rows sharing this key; confirm the intended single event before producing a corrected file. Do not resend billing events.",
    "UNBILLED_EVENT": "Confirm the provided source event is billable and in the agreed period before correcting a billed export; do not automatically bill or resend.",
    "BILLED_WITHOUT_SOURCE": "Check whether the source export omitted this event; establish source completeness for this key before changing any bill.",
    "QUANTITY_MISMATCH": "Inspect both original event rows and the agreed quantity rule; provide a corrected export only after deciding which record is authoritative.",
    "UNIT_MISMATCH": "Provide event-level exports using the same agreed supported unit; do not infer or convert units.",
    "ATOMIC_SCOPE_UNCONFIRMED": "Confirm both files describe pre-agreed one-to-one atomic events in the same scope; otherwise obtain event-level exports.",
}
DEFAULT_ACTION = "Provide a valid event-level UTF-8 CSV using the documented schema, supported units and quantity bounds; do not infer a Ready result."


def finding(code, severity="unknown", **detail):
    return {"code": code, "severity": severity, "next_action": ACTIONS.get(code, DEFAULT_ACTION), **detail}


def parse_csv(data, side):
    problems, records = [], []
    if not data or len(data) > MAX_FILE_BYTES:
        return records, [finding("EMPTY_OR_OVERSIZE_FILE", side=side)], 0
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError:
        return records, [finding("INVALID_UTF8", side=side)], 0
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        if next(reader, None) != FIELDS:
            return records, [finding("INVALID_SCHEMA", side=side)], 0
        row_count = 0
        for row_count, row in enumerate(reader, 1):
            if row_count > MAX_ROWS:
                return [], [finding("ROW_LIMIT", side=side)], row_count
            detail = {"side": side, "record": row_count, "ending_line": reader.line_num}
            if len(row) != len(FIELDS):
                problems.append(finding("INVALID_COLUMN_COUNT", **detail))
                continue
            event, customer, period, unit, quantity = row
            if (not event.strip() or not customer.strip() or
                    len(event) > 128 or len(customer) > 128 or "\x00" in event + customer):
                problems.append(finding("INVALID_IDENTIFIER", **detail))
                continue
            if event.strip().upper() in {"TOTAL", "AGGREGATE", "SUMMARY"}:
                problems.append(finding("UNSUPPORTED_AGGREGATE", **detail))
                continue
            if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", period) or period.startswith("0000"):
                problems.append(finding("INVALID_PERIOD", **detail))
                continue
            if unit not in UNITS:
                problems.append(finding("UNSUPPORTED_UNIT", **detail))
                continue
            if not re.fullmatch(r"(?:0|[1-9][0-9]{0,12})(?:\.[0-9]{1,6})?", quantity):
                problems.append(finding("INVALID_QUANTITY", **detail))
                continue
            amount = Decimal(quantity)
            if not amount.is_finite() or amount < 0 or amount > MAX_QUANTITY:
                problems.append(finding("INVALID_QUANTITY", **detail))
                continue
            records.append({"key": (customer, period, event), "unit": unit,
                            "quantity": amount, "record": row_count})
        if not row_count:
            problems.append(finding("NO_DATA_ROWS", side=side))
        return records, problems, row_count
    except csv.Error:
        return [], [finding("MALFORMED_CSV", side=side)], 0


def reconcile(usage_bytes, billed_bytes, confirm_atomic_events=False):
    usage, usage_problems, usage_count = parse_csv(usage_bytes, "usage")
    billed, billed_problems, billed_count = parse_csv(billed_bytes, "billed")
    findings = usage_problems + billed_problems
    if confirm_atomic_events is not True:
        findings.append(finding("ATOMIC_SCOPE_UNCONFIRMED"))
    matched = 0
    if not findings:
        source, invoices = defaultdict(list), defaultdict(list)
        for item in usage:
            source[item["key"]].append(item)
        for item in billed:
            invoices[item["key"]].append(item)
        for key in sorted(source.keys() | invoices.keys()):
            detail = {"customer_id": key[0], "period": key[1], "event_id": key[2]}
            left, right = source[key], invoices[key]
            for rows, side, code in [(left, "usage", "DUPLICATE_SOURCE_EVENT"),
                                     (right, "billed", "DUPLICATE_BILLED_EVENT")]:
                if len(rows) > 1:
                    findings.append(finding(code, "error", side=side,
                                            records=[x["record"] for x in rows], **detail))
            if not right:
                findings.append(finding("UNBILLED_EVENT", "error", **detail))
            elif not left:
                findings.append(finding("BILLED_WITHOUT_SOURCE", "error", **detail))
            elif len(left) == len(right) == 1:
                before, after = left[0], right[0]
                if before["unit"] != after["unit"]:
                    findings.append(finding("UNIT_MISMATCH", usage_unit=before["unit"],
                                            billed_unit=after["unit"], **detail))
                elif before["quantity"] != after["quantity"]:
                    findings.append(finding("QUANTITY_MISMATCH", "error",
                                            usage_quantity=str(before["quantity"]),
                                            billed_quantity=str(after["quantity"]), **detail))
                else:
                    matched += 1
    errors = sum(x["severity"] == "error" for x in findings)
    unknowns = sum(x["severity"] == "unknown" for x in findings)
    return {
        "policy_version": POLICY_VERSION,
        "state": "Unknown" if unknowns else "Failed" if errors else "Ready",
        "scope": "Provided records only; caller-declared atomic event scope. No source completeness, money/tax, API or customer acceptance verified.",
        "atomic_scope_caller_declared": confirm_atomic_events is True,
        "inputs": {side: {"sha256": hashlib.sha256(data).hexdigest() if len(data) <= MAX_FILE_BYTES else None,
                          "bytes": len(data) if len(data) <= MAX_FILE_BYTES else None,
                          "hash_scope": "exact_provided_bytes" if len(data) <= MAX_FILE_BYTES else "unavailable_oversize",
                          "observed_bytes": len(data)}
                   for side, data in [("usage", usage_bytes), ("billed", billed_bytes)]},
        "counts": {"usage_rows": usage_count, "billed_rows": billed_count,
                   "valid_usage_rows": len(usage), "valid_billed_rows": len(billed),
                   "matched_events": matched, "error_findings": errors,
                   "unknown_findings": unknowns},
        "findings": findings,
    }
