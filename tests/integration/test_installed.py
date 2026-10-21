"""Exercise installed commands from outside the checkout with synthetic data."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CONTRACT = {'x-schema': 'truquence.workflow-contract.v0.2', 'x-source': 'make',
            'x-scope': 'execution_observation', 'x-scenario_id': 1229,
            'x-execution_id': 'run-1', 'x-expect_operations': 10}
EXECUTION = {'id': 'run-1', 'imtId': '1632371744497_scenario.1229.auto.run-1',
             'type': 'auto', 'status': 1, 'operations': 10}


def command(name):
    return str(Path(sys.executable).with_name(name))


class InstalledCommands(unittest.TestCase):
    def test_help_and_receipt_reverification(self):
        with tempfile.TemporaryDirectory(prefix='tq-installed-') as folder:
            folder = str(Path(folder).resolve())
            env = dict(os.environ, HOME=folder, CLAUDE_CONFIG_DIR=folder + '/settings')
            for name in ('truquence', 'truquence-mcp', 'truquence-recorder'):
                result = subprocess.run([command(name), '--help'], cwd=folder, env=env,
                                        capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
            event = {'hook_event_name': 'PreToolUse', 'session_id': 'synthetic',
                     'cwd': '/example', 'tool_name': 'Bash', 'tool_use_id': 'synthetic-1',
                     'tool_input': {'command': 'echo hello'}}
            for kind in ('PreToolUse', 'PostToolUse'):
                event['hook_event_name'] = kind
                result = subprocess.run([command('truquence-recorder'), 'hook'],
                                        input=json.dumps(event).encode(), cwd=folder, env=env,
                                        capture_output=True, timeout=15)
                self.assertEqual((result.returncode, result.stdout), (0, b'{}\n'), result.stderr)
            def verify():
                result = subprocess.run([command('truquence-recorder'), 'verify'], cwd=folder,
                                        env=env, capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)
            first = verify()
            self.assertEqual(first['records'], 2)
            self.assertEqual(first['integrity'], 'SELF_CONSISTENT')
            self.assertEqual(first['authenticity'], 'UNKNOWN')
            self.assertEqual(first['completeness'], 'UNKNOWN')
            ledger = Path(folder) / '.local/state/truquence-recorder/actions.jsonl'
            rows = [json.loads(line) for line in ledger.read_text().splitlines()]
            self.assertEqual({r['evidence_level'] for r in rows}, {'self_reported'})
            # Replay retained bytes under a different isolated home, without the producer.
            with tempfile.TemporaryDirectory(prefix='tq-replay-') as replay:
                destination = Path(replay) / '.local/state/truquence-recorder/actions.jsonl'
                destination.parent.mkdir(parents=True, mode=0o700)
                shutil.copyfile(ledger, destination)
                env['HOME'] = str(Path(replay).resolve())
                self.assertEqual(verify(), first)
                row = json.loads(destination.read_text().splitlines()[0])
                row['tool'] = 'tampered'
                destination.write_text(json.dumps(row) + '\n' + ledger.read_text().splitlines()[1] + '\n')
                bad = subprocess.run([command('truquence-recorder'), 'verify'], cwd=folder,
                                     env=env, capture_output=True, timeout=15)
                self.assertEqual(bad.returncode, 1)
            print('recorder_replay=' + json.dumps(first, sort_keys=True))


class InstalledMCP(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_loads_and_verifies(self):
        with tempfile.TemporaryDirectory(prefix='tq-mcp-client-') as folder:
            parameters = StdioServerParameters(command=command('truquence-mcp'), cwd=folder)
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), 15)
                    tools = await session.list_tools()
                    self.assertEqual([t.name for t in tools.tools], ['truquence_accept'])
                    async def call(contract, execution):
                        return await asyncio.wait_for(session.call_tool('truquence_accept', {
                            'contract_json': json.dumps(contract), 'execution_json': json.dumps(execution),
                            'source': 'make'}), 15)
                    for execution, expected in ((EXECUTION, 'PASS'),
                                                (dict(EXECUTION, operations=9), 'FAIL'), ({}, 'UNKNOWN')):
                        result = await call(CONTRACT, execution)
                        self.assertFalse(result.isError)
                        value = json.loads(result.content[0].text)
                        self.assertEqual(value['status'], expected)
                        self.assertEqual(value['gateBlocked'], expected != 'PASS')
                        self.assertEqual(value['evidence_level'], 'imported')
                        self.assertEqual(value['report']['business_acceptance'], 'UNKNOWN')
                        print('mcp_result=' + json.dumps({k: value[k] for k in ('status', 'gateBlocked', 'evidence_level')}))
                    for text in ('{', '{"a":1,"a":2}', ' ' * (1048576 + 1)):
                        result = await asyncio.wait_for(session.call_tool('truquence_accept', {
                            'contract_json': json.dumps(CONTRACT), 'execution_json': text, 'source': 'make'}), 15)
                        self.assertTrue(result.isError)
                    result = await session.call_tool('truquence_accept', {
                        'contract_json': '{}', 'execution_json': '{}', 'source': 'unsupported'})
                    self.assertTrue(result.isError)


if __name__ == '__main__':
    unittest.main()
