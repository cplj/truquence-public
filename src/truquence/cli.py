"""Reconcile two provided atomic-event CSV files and exclusively create a JSON report."""
import argparse
import json
import sys
from pathlib import Path
if __package__:
    from . import __version__
    from .core import MAX_FILE_BYTES, reconcile
else:
    from __init__ import __version__
    from core import MAX_FILE_BYTES, reconcile


def read_bounded(path):
    with Path(path).open("rb") as handle:
        return handle.read(MAX_FILE_BYTES + 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog="Workflow commands: truquence init --help; truquence accept --format n8n --help; truquence accept --help (three checker inputs).")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("usage")
    parser.add_argument("billed")
    parser.add_argument("--out", required=True)
    parser.add_argument("--confirm-atomic-events", action="store_true")
    args = parser.parse_args()
    try:
        input_path = args.usage
        usage = read_bounded(input_path)
        input_path = args.billed
        billed = read_bounded(input_path)
        input_path = None
        result = reconcile(usage, billed, args.confirm_atomic_events)
        payload = (json.dumps(result, ensure_ascii=True, indent=2) + "\n").encode("utf-8")
        with Path(args.out).open("xb") as handle:
            handle.write(payload)
    except (OSError, ValueError) as error:
        print(json.dumps({"operation": "export_failed", "state": "Unknown",
                          "error": type(error).__name__, "path": input_path or args.out,
                          "detail": str(error),
                          "next_action": ("Correct the input path or permissions, then rerun with readable CSV files and a fresh output path."
                                          if input_path else "No completed result. Retain any partial output and reconcile before retrying; use a new output path.")}), file=sys.stderr)
        return 2
    print(json.dumps({"operation": "exported", "state": result["state"], "output": args.out}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
