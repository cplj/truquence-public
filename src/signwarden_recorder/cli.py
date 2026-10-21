"""Command line interface.

Modified 2026-10-20: public capture-only cut, no rule matching; expose capture installation and chain verification only.
"""
import sys


def main():
    if sys.argv[1:] == ['hook']:
        from .hook import main as hook_main
        return hook_main()
    import argparse
    from .core import canonical
    parser = argparse.ArgumentParser(prog='swr', description='Local tool-call recorder. No data is uploaded.')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('install', 'uninstall', 'verify', 'hook'):
        sub.add_parser(name)
    args = parser.parse_args()
    try:
        if args.command in ('install', 'uninstall'):
            from . import install
            print(getattr(install, args.command)())
        elif args.command == 'verify':
            from .storage import GENESIS, read_records
            rows = read_records()
            print(canonical({'integrity': 'SELF_CONSISTENT', 'records': len(rows),
                             'head': rows[-1]['hash'] if rows else GENESIS,
                             'completeness': 'UNKNOWN', 'authenticity': 'UNKNOWN'}).decode())
    except (ValueError, OSError) as exc:
        print('swr: ' + str(exc), file=sys.stderr)
        return 1
    return 0
