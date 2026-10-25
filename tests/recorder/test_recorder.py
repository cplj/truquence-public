"""Synthetic checks for the public capture-only cut; no rule matching.

Fixtures are retained for inspection. No real user settings are read or modified.
"""
import ast
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import random
import shlex
import socket
import subprocess
import sys
import tempfile
import time
try:
    import tomllib
except ImportError:
    import tomli as tomllib
import unittest
from unittest.mock import patch

from truquence_recorder.core import MAX_INPUT, canonical, digest, hook_input, parse, redact, summarize
from truquence_recorder.hook import handle
from truquence_recorder import install, native, storage, worker

PACKAGE = Path(__file__).resolve().parents[2]
FIXTURES = Path(tempfile.mkdtemp(prefix='swr-public-test-',
    dir='/private/tmp' if sys.platform == 'darwin' else None)).resolve()


def event(kind='PreToolUse', call='synthetic-call'):
    return {'hook_event_name': kind, 'session_id': 'synthetic-session', 'cwd': '/example',
            'tool_name': 'Bash', 'tool_use_id': call, 'tool_input': {'command': 'echo hello'}}


def generated_json(rng, depth=0):
    scalar = [None, True, False, rng.randint(-2**63, 2**63), rng.random(),
              ''.join(chr(rng.randrange(0x110000)) for _ in range(rng.randrange(12)))]
    if depth == 4 or rng.randrange(3) == 0:
        return rng.choice(scalar)
    if rng.randrange(2):
        return [generated_json(rng, depth + 1) for _ in range(rng.randrange(5))]
    return {str(rng.randrange(100)): generated_json(rng, depth + 1)
            for _ in range(rng.randrange(5))}


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix='home-', dir=FIXTURES))
        self.env = patch.dict(os.environ, {'HOME': str(self.home),
            'CLAUDE_CONFIG_DIR': str(self.home / '.claude'), 'PYTHONDONTWRITEBYTECODE': '1'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def invoke(self, *args, raw=b''):
        return subprocess.run([sys.executable, '-B', '-m', 'truquence_recorder', *args],
            input=raw, capture_output=True, cwd=PACKAGE, timeout=10)

    def test_capture_and_pair(self):
        self.assertEqual(handle(hook_input(canonical(event()))), {})
        post = event('PostToolUse')
        post['tool_response'] = {'exit_code': 0, 'output': 'not collected'}
        self.assertEqual(handle(hook_input(canonical(post))), {})
        rows = storage.read_records()
        self.assertEqual([r['status'] for r in rows], ['requested', 'succeeded'])
        self.assertEqual([r['risks'] for r in rows], [[], []])
        self.assertEqual([r['evidence_level'] for r in rows], ['self_reported', 'self_reported'])
        self.assertGreaterEqual(rows[1]['elapsed_ms'], 0)
        self.assertNotIn('not collected', (storage.root() / 'actions.jsonl').read_text())
        self.assertEqual((storage.root() / 'actions.jsonl').stat().st_mode & 0o777, 0o600)

    def test_legacy_pair_does_not_propagate_risks(self):
        handle(event())
        old = storage.read_records()[0]
        old['risks'] = ['synthetic-legacy-label']
        old['hash'] = digest({k: v for k, v in old.items() if k != 'hash'})
        (storage.root() / 'actions.jsonl').write_bytes(canonical(old) + b'\n')
        handle(event('PostToolUse'))
        rows = storage.read_records()
        self.assertEqual(rows[0]['risks'], ['synthetic-legacy-label'])
        self.assertEqual(rows[1]['risks'], [])
        self.assertGreaterEqual(rows[1]['elapsed_ms'], 0)

    def test_all_events(self):
        for kind in ['SessionStart', 'PreToolUse', 'PostToolUse', 'PostToolUseFailure', 'SessionEnd']:
            self.assertEqual(handle(hook_input(canonical(event(kind)))), {})
        self.assertEqual(len(storage.read_records()), 5)

    def test_bad_inputs(self):
        cases = [b'null', b'[]', b'{}', b'{"a":1,"a":2}', b'{"a":NaN}',
                 b'{"a":1e999}', b'\xff', b'{', b'x' * (MAX_INPUT + 1),
                 b'[' * 2000 + b']' * 2000]
        for raw in cases:
            with self.subTest(raw_length=len(raw)), self.assertRaises(ValueError):
                hook_input(raw)

    def test_metadata_limits(self):
        for key, length in [('session_id', 4097), ('cwd', 4097), ('tool_name', 257), ('tool_use_id', 4097)]:
            value = event(); value[key] = 'x' * length
            with self.subTest(key=key), self.assertRaises(ValueError):
                hook_input(canonical(value))
        for key, value in [('tool_input', []), ('tool_name', ''), ('session_id', 1), ('cwd', '')]:
            data = event(); data[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                hook_input(canonical(data))

    def test_generated_json_and_redaction_properties(self):
        rng = random.Random(20261020)
        for _ in range(500):
            value = generated_json(rng)
            self.assertEqual(parse(canonical(value)), value)
            self.assertEqual(redact(redact(value)), redact(value))
        for _ in range(500):
            raw = rng.randbytes(rng.randrange(256))
            try:
                value = parse(raw)
            except ValueError:
                continue
            self.assertEqual(parse(canonical(value)), value)

    def test_generated_secret_removal_and_nonsecret_preservation(self):
        rng = random.Random(20261021)
        for _ in range(300):
            secret = ''.join(rng.choice('abcdefghijk0123456789') for _ in range(rng.randrange(16, 65)))
            encoded = base64.b64encode(('user:' + secret).encode()).decode()
            cases = [{'password': secret}, {'nested': [{'api_key': secret}]},
                     'Bearer ' + secret, 'Basic ' + encoded, 'sk_live_' + secret,
                     'hf_' + secret, 'curl -u user:' + secret,
                     {'argv': ['client', '--token', secret]}]
            for value in cases:
                masked = redact(value)
                self.assertNotIn(secret, canonical(masked).decode())
                self.assertNotIn(encoded, canonical(masked).decode())
                self.assertEqual(redact(masked), masked)
            value = {rng.choice(['max_tokens', 'token_count', 'tokenizer']): rng.randint(-10**12, 10**12),
                     'command': 'echo hello; Basic usage'}
            self.assertEqual(redact(value), value)
            self.assertEqual(summarize(value), value)

    def test_secret_capture_and_summary_limits(self):
        value = event()
        value['tool_input'] = {'api_key': 'synthetic-value-123456', 'content': 'private text',
                               'command': 'echo --token synthetic-value-123456', 'long': 'x' * 5000}
        handle(hook_input(canonical(value)))
        row = storage.read_records()[0]
        self.assertNotIn('synthetic-value-123456', canonical(row).decode())
        self.assertNotIn('private text', canonical(row).decode())
        self.assertEqual(len(row['arguments']['long']), 2048)
        self.assertEqual(summarize({str(i): 'x' * 2048 for i in range(20)}),
                         {'summary': '[OMITTED: arguments exceed summary limit]'})
        self.assertNotIn('\x1b', redact('\x1b]52;c;data\x07'))
        self.assertNotIn('\u202e', redact('\u202e'))

    def test_tamper_and_incomplete_tail(self):
        for change in ['middle', 'tail', 'truncate']:
            home = self.home / change; home.mkdir(mode=0o700)
            with patch.dict(os.environ, {'HOME': str(home)}):
                handle(event()); handle(event(call='second'))
                path = storage.root() / 'actions.jsonl'; raw = path.read_bytes()
                if change == 'truncate':
                    path.write_bytes(raw[:-1])
                elif change == 'middle':
                    path.write_bytes(raw.replace(b'echo hello', b'echo other', 1))
                else:
                    lines = raw.splitlines(); lines[-1] = lines[-1].replace(b'echo hello', b'echo other')
                    path.write_bytes(b'\n'.join(lines) + b'\n')
                with self.assertRaises(ValueError): storage.read_records()
                if change != 'middle':
                    with self.assertRaises(ValueError): handle(event())
                self.assertEqual(self.invoke('verify').returncode, 1)

    def test_symlink_and_permissions(self):
        getattr(storage, 'private' + '_dir')(storage.root())
        target = self.home / 'untouched'; target.write_text('original')
        (storage.root() / 'actions.jsonl').symlink_to(target)
        with self.assertRaises(OSError): handle(event())
        self.assertEqual(target.read_text(), 'original')
        unsafe = self.home / 'unsafe'; unsafe.mkdir(mode=0o755)
        with self.assertRaises(ValueError): getattr(storage, 'private' + '_dir')(unsafe)

    def test_concurrent_append(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda i: handle(event(call=str(i))), range(40)))
        self.assertEqual([r['seq'] for r in storage.read_records()], list(range(40)))

    def test_cli_hook_verify_and_failure(self):
        result = self.invoke('hook', raw=canonical(event()))
        self.assertEqual((result.returncode, result.stdout), (0, b'{}\n'))
        row = json.loads(self.invoke('verify').stdout)
        self.assertEqual(row['records'], 1)
        self.assertEqual(row['completeness'], 'UNKNOWN')
        self.assertEqual(row['authenticity'], 'UNKNOWN')
        bad = self.invoke('hook', raw=b'{"password":"synthetic-private",')
        self.assertEqual(bad.returncode, 1)
        self.assertNotIn(b'synthetic-private', bad.stderr)
        self.assertEqual(len(storage.read_records()), 1)
        help_text = self.invoke('--help').stdout.decode()
        self.assertIn('{install,uninstall,verify,hook}', help_text)

    def test_install_restore_synthetic_settings(self):
        path = install.settings_path(); path.parent.mkdir(mode=0o700)
        original = b'{ "example": true }\n'; path.write_bytes(original); path.chmod(0o640)
        self.assertIn('installed', install.install())
        self.assertEqual(install.install(), 'already installed')
        installed = json.loads(path.read_bytes())
        self.assertEqual(set(installed['hooks']), {'SessionStart', 'PreToolUse', 'PostToolUse', 'PostToolUseFailure', 'SessionEnd'})
        self.assertIn('original settings restored', install.uninstall())
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(path.stat().st_mode & 0o777, 0o640)
        self.assertTrue((storage.root() / 'settings.backup').exists())

    def test_install_preserves_later_changes(self):
        path = install.settings_path(); path.parent.mkdir(mode=0o700); path.write_text('{}')
        install.install()
        config = json.loads(path.read_bytes()); config['later'] = True
        path.write_bytes(canonical(config))
        self.assertIn('later settings preserved', install.uninstall())
        self.assertEqual(json.loads(path.read_bytes()), {'later': True})

    def test_worker_receive(self):
        sender, receiver = socket.socketpair()
        with sender, receiver:
            sender.sendall(b'abc'); sender.shutdown(socket.SHUT_WR)
            self.assertEqual(worker.receive(receiver, 3), b'abc')
            with self.assertRaises(ValueError): worker.receive(receiver, 1)

    def test_native_capture_and_failure(self):
        command = shlex.split(native.hook_command())[1:]
        runner = Path(command[-1])
        h = 14695981039346656037
        for byte in os.fsencode(str(self.home)) + os.fsencode(str(runner)):
            h = ((h ^ byte) * 1099511628211) & ((1 << 64) - 1)
        tmp = Path('/private/tmp' if sys.platform == 'darwin' else '/tmp')
        directory = tmp / ('swr-%d-%016x' % (os.getuid(), h))
        self.assertFalse(directory.exists())
        directory.mkdir(mode=0o700)
        proc = subprocess.Popen([sys.executable, '-B', '-S', str(runner), '--worker', str(directory)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not (directory / 'socket').exists() and time.monotonic() < deadline:
                self.assertIsNone(proc.poll()); time.sleep(0.01)
            self.assertTrue((directory / 'socket').exists())
            for raw, expected in [(canonical(event()), 0), (b'{', 1), (b'x' * (MAX_INPUT + 1), 1)]:
                result = subprocess.run(command, input=raw, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, expected, result.stderr)
                if expected == 0: self.assertEqual(result.stdout, b'{}\n')
            self.assertEqual(len(storage.read_records()), 1)
            self.assertEqual(self.invoke('verify').returncode, 0)
        finally:
            proc.terminate(); _, errors = proc.communicate(timeout=5)
            self.assertEqual(proc.returncode, 0, errors)
            print('native_transport_fixture=' + str(directory))

    def test_manifest_and_import_closure(self):
        spec = tomllib.loads((PACKAGE / 'pyproject.toml').read_text())
        self.assertEqual(spec['project']['name'], 'truquence')
        self.assertEqual(spec['project']['dependencies'], [])
        self.assertEqual(spec['tool']['setuptools']['package-data']['truquence_recorder'], ['client.c'])
        self.assertEqual({'truquence', 'truquence-mcp', 'truquence-recorder'}, set(spec['project']['scripts']))
        allowed = {'__init__', '__main__', 'cli', 'client', 'core', 'hook', 'install', 'native', 'runner', 'storage', 'worker'}
        files = [p for p in (PACKAGE / 'src/truquence_recorder').iterdir() if p.is_file()]
        self.assertEqual({p.stem for p in files}, allowed)
        for path in files:
            if path.suffix != '.py': continue
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.level:
                        if node.module: self.assertIn(node.module.split('.')[0], allowed)
                        else:
                            for alias in node.names: self.assertIn(alias.name, allowed)
                    elif node.module.split('.')[0] != 'truquence_recorder':
                        self.assertIn(node.module.split('.')[0], sys.stdlib_module_names)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertIn(alias.name.split('.')[0], sys.stdlib_module_names)


def tearDownModule():
    print('retained_synthetic_fixtures=' + str(FIXTURES))


if __name__ == '__main__':
    unittest.main()
