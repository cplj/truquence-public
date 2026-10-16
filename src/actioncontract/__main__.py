"""Local Action Contract acceptance CLI (Python standard library only)."""
import argparse
import json
from pathlib import Path
import sys

from .acceptance import accept, markdown


def main():
    parser = argparse.ArgumentParser(prog="truquence")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("accept", help="merge three native synthetic checker results")
    command.add_argument("--contract", required=True)
    command.add_argument("--results", nargs=3, required=True, metavar=("AUTHORIZATION", "RECOVERY", "COMPLETION"),
                         help="ordered files: authorization (signwarden), recovery (axiocairn), completion (kinesift)")
    command.add_argument("--out", default="acceptance", help="new JSON/Markdown output prefix")
    command.add_argument("--expect-contract-hash")
    command.add_argument("--expect-results-hash", nargs=3)
    args = parser.parse_args()
    report = accept(args.contract, args.results, args.expect_contract_hash, args.expect_results_hash)
    try:
        data = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        rendered = markdown(report)
        # Reserve both files before writing; never overwrite prior evidence.
        with Path(args.out + ".json").open("x", encoding="utf-8") as json_file:
            with Path(args.out + ".md").open("x", encoding="utf-8") as md_file:
                json_file.write(data)
                md_file.write(rendered)
    except (OSError, MemoryError) as error:
        print(json.dumps({"status": "UNKNOWN", "error": "INPUT_RESOURCE_LIMIT" if isinstance(error, MemoryError) else str(error),
                          "next_action": "Retain partial outputs; reconcile them and choose a new output prefix."}), file=sys.stderr)
        return 3
    print(data, end="")
    return {"PASS": 0, "FAIL": 1, "UNKNOWN": 2}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
