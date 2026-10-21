"""Optional MCP stdio interface to the public offline workflow verifier."""
import argparse
from pathlib import Path
import sys
import tempfile
from typing import Literal

from actioncontract import decode
from . import workflow


def truquence_accept(contract_json: str, execution_json: str,
                     source: Literal['n8n', 'make'] = 'n8n') -> dict:
    """Verify supplied workflow JSON against explicit expectations, offline.

    Inputs are JSON text, never paths or URLs; each is limited to 1 MiB.
    Evidence level is imported. PASS concerns supplied records only;
    business acceptance and real external effects remain UNKNOWN.
    FAIL and UNKNOWN block acceptance and never authorize retries.
    """
    if source not in ('n8n', 'make'):
        raise ValueError('source must be n8n or make')
    with tempfile.TemporaryDirectory(prefix='truquence-mcp-') as directory:
        paths = []
        for name, text in (('contract', contract_json), ('execution', execution_json)):
            if not isinstance(text, str) or not 0 < len(text) <= workflow.LIMIT:
                raise ValueError('Expected 1 byte to 1 MiB of JSON text')
            raw = text.encode('utf-8')
            if len(raw) > workflow.LIMIT:
                raise ValueError('JSON input exceeds 1 MiB')
            try:
                decode(raw)
            except (RecursionError, OverflowError) as exc:
                raise ValueError('Invalid JSON depth or number') from exc
            path = Path(directory) / (name + '.json')
            path.write_bytes(raw)
            paths.append(path)
        report = workflow.accept(*paths, source)
    return {'status': report['status'], 'accepted': report['status'] == 'PASS',
            'gateBlocked': report['status'] != 'PASS', 'evidence_level': 'imported',
            'report': report}


def main():
    parser = argparse.ArgumentParser(prog='truquence-mcp', description=__doc__)
    parser.parse_args()
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print('Install truquence[mcp] to run the stdio server.', file=sys.stderr)
        return 2
    server = FastMCP('Truquence', instructions='Supplied evidence only. FAIL and UNKNOWN block acceptance.')
    server.tool()(truquence_accept)
    server.run(transport='stdio')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
