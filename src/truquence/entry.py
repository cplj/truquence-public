"""Installed command for workflow acceptance and supplied-record reconciliation."""
import sys


def main():
    if not sys.argv[1:] or sys.argv[1:] in (["--help"], ["-h"]):
        print("""usage: truquence accept --contract CONTRACT --results AUTHORIZATION RECOVERY COMPLETION --out PREFIX
       truquence USAGE.csv BILLED.csv --confirm-atomic-events --out REPORT.json

accept  Merge supplied synthetic authorization, recovery and completion evidence.
        truquence accept --help
CSV     Compare supplied atomic-event CSV files; export success is not acceptance.
        truquence usage.csv billed.csv --confirm-atomic-events --out report.json

More commands: init --help; accept --format n8n --help.
Use fresh output paths. Run each command's --help for required inputs.""")
        return 0 if sys.argv[1:] else 2
    if sys.argv[1:2] == ['init'] or (sys.argv[1:2] == ['accept'] and
                                       any(a == '--format' or a.startswith('--format=') for a in sys.argv)):
        from .workflow import main as run
    elif sys.argv[1:2] == ['accept']:
        from actioncontract.__main__ import main as run
    else:
        from .cli import main as run
    return run()


if __name__ == '__main__':
    sys.exit(main())
