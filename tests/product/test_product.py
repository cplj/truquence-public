"""Contract tests against the installed product; all data is synthetic."""
import base64
import hashlib
import http.client
import importlib.resources
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from truquence import __version__
from truquence.core import FIELDS, MAX_FILE_BYTES, MAX_ROWS, parse_csv, reconcile
from truquence.server import HTTPServer, Handler, MAX_BODY_BYTES

HEADER = (','.join(FIELDS) + '\n').encode()
ROW = b'e1,c1,2026-10,request,2\n'
CSV = HEADER + ROW
ASSETS = importlib.resources.files('truquence')


class CoreTests(unittest.TestCase):
    def test_ready_and_exact_input_hash(self):
        result = reconcile(CSV, CSV, True)
        self.assertEqual(result['state'], 'Ready')
        self.assertEqual(result['counts']['matched_events'], 1)
        self.assertEqual(result['findings'], [])
        self.assertEqual(result['inputs']['usage']['sha256'], hashlib.sha256(CSV).hexdigest())

    def test_dirty_then_corrected(self):
        source = ASSETS.joinpath('samples/usage.csv').read_bytes()
        dirty = reconcile(source, ASSETS.joinpath('samples/billed_dirty.csv').read_bytes(), True)
        self.assertEqual(dirty['state'], 'Failed')
        self.assertEqual({f['code'] for f in dirty['findings']}, {'DUPLICATE_BILLED_EVENT', 'UNBILLED_EVENT'})
        clean = reconcile(source, ASSETS.joinpath('samples/billed_clean.csv').read_bytes(), True)
        self.assertEqual(clean['state'], 'Ready')
        self.assertEqual(clean['counts']['matched_events'], 3)

    def test_unknown_without_scope_confirmation(self):
        for confirmation in (False, None, 1, 'true'):
            with self.subTest(confirmation=confirmation):
                result = reconcile(CSV, CSV, confirmation)
                self.assertEqual(result['state'], 'Unknown')
                self.assertIn('ATOMIC_SCOPE_UNCONFIRMED', {f['code'] for f in result['findings']})

    def test_definite_differences(self):
        cases = [
            (HEADER + ROW + ROW, CSV, 'DUPLICATE_SOURCE_EVENT'),
            (CSV, HEADER + ROW + ROW, 'DUPLICATE_BILLED_EVENT'),
            (HEADER + ROW + b'e2,c1,2026-10,request,1\n', CSV, 'UNBILLED_EVENT'),
            (CSV, HEADER + ROW + b'e2,c1,2026-10,request,1\n', 'BILLED_WITHOUT_SOURCE'),
            (CSV, HEADER + ROW.replace(b',2\n', b',3\n'), 'QUANTITY_MISMATCH'),
        ]
        for usage, billed, code in cases:
            with self.subTest(code=code):
                result = reconcile(usage, billed, True)
                self.assertEqual(result['state'], 'Failed')
                self.assertIn(code, {f['code'] for f in result['findings']})
                self.assertTrue(all(f['next_action'] for f in result['findings']))

    def test_unknown_input_cases(self):
        cases = [
            (b'', 'EMPTY_OR_OVERSIZE_FILE'),
            (HEADER, 'NO_DATA_ROWS'),
            (b'\xff', 'INVALID_UTF8'),
            (b'customer_id,quantity\nc1,2\n', 'INVALID_SCHEMA'),
            (HEADER + b'"unfinished', 'MALFORMED_CSV'),
            (HEADER + b'e1,c1\n', 'INVALID_COLUMN_COUNT'),
            (HEADER + ROW.replace(b'e1,', b',', 1), 'INVALID_IDENTIFIER'),
            (HEADER + ROW.replace(b'e1,', b'TOTAL,', 1), 'UNSUPPORTED_AGGREGATE'),
            (HEADER + ROW.replace(b'2026-10', b'2026-13'), 'INVALID_PERIOD'),
            (HEADER + ROW.replace(b'2026-10', b'0000-01'), 'INVALID_PERIOD'),
            (HEADER + ROW.replace(b'request', b'dollar'), 'UNSUPPORTED_UNIT'),
            (HEADER + ROW.replace(b',2\n', b',-1\n'), 'INVALID_QUANTITY'),
        ]
        for data, code in cases:
            with self.subTest(code=code, data=data):
                result = reconcile(CSV, data, True)
                self.assertEqual(result['state'], 'Unknown')
                self.assertIn(code, {f['code'] for f in result['findings']})
                self.assertEqual(result['counts']['matched_events'], 0)

    def test_unit_mismatch_is_unknown(self):
        result = reconcile(CSV, CSV.replace(b'request', b'token'), True)
        self.assertEqual(result['state'], 'Unknown')
        self.assertEqual(result['findings'][0]['code'], 'UNIT_MISMATCH')

    def test_quantity_boundaries(self):
        for quantity in (b'0', b'0.000001', b'1000000000000', b'2.000000'):
            with self.subTest(quantity=quantity):
                data = HEADER + ROW.replace(b',2\n', b',' + quantity + b'\n')
                self.assertEqual(reconcile(data, data, True)['state'], 'Ready')
        for quantity in (b'1000000000000.000001', b'0.0000001', b'01', b'1e2', b'NaN', b'+2', b' 2'):
            with self.subTest(quantity=quantity):
                data = HEADER + ROW.replace(b',2\n', b',' + quantity + b'\n')
                self.assertEqual(reconcile(data, data, True)['state'], 'Unknown')

    def test_identifier_and_field_boundaries(self):
        for size, expected in ((128, 'Ready'), (129, 'Unknown'), (4097, 'Unknown')):
            with self.subTest(size=size):
                data = HEADER + ROW.replace(b'e1,', b'x' * size + b',', 1)
                self.assertEqual(reconcile(data, data, True)['state'], expected)

    def test_byte_limit(self):
        for size, oversize in ((MAX_FILE_BYTES, False), (MAX_FILE_BYTES + 1, True)):
            with self.subTest(size=size):
                result = reconcile(b'x' * size, CSV, True)
                self.assertEqual(result['state'], 'Unknown')
                codes = {f['code'] for f in result['findings']}
                self.assertEqual('EMPTY_OR_OVERSIZE_FILE' in codes, oversize)
                self.assertEqual(result['inputs']['usage']['sha256'] is None, oversize)

    def test_row_limit(self):
        for count, expected in ((MAX_ROWS, []), (MAX_ROWS + 1, ['ROW_LIMIT'])):
            with self.subTest(count=count):
                _, problems, observed = parse_csv(HEADER + ROW * count, 'usage')
                self.assertEqual([f['code'] for f in problems], expected)
                self.assertEqual(observed, count)

    def test_bom_and_decimal_equivalence(self):
        result = reconcile(b'\xef\xbb\xbf' + CSV, CSV.replace(b',2\n', b',2.0\n'), True)
        self.assertEqual(result['state'], 'Ready')


class CLITests(unittest.TestCase):
    def setUp(self):
        # Retain temp files: no cleanup/delete operations are needed for these tests.
        self.work = Path(tempfile.mkdtemp(prefix='truquence-cli-'))
        self.usage = self.work / 'usage.csv'
        self.billed = self.work / 'billed.csv'
        self.output = self.work / 'result.json'
        self.usage.write_bytes(CSV)
        self.billed.write_bytes(CSV)
        self.command = str(Path(sys.executable).with_name('truquence'))

    def run_cli(self, *args):
        return subprocess.run([self.command, *map(str, args)], cwd=self.work,
                              capture_output=True, text=True, timeout=10)

    def test_installed_help_and_version(self):
        self.assertEqual(__version__, '0.3.0')
        self.assertIn('0.3.0', self.run_cli('--version').stdout)
        help_result = self.run_cli('--help')
        self.assertEqual(help_result.returncode, 0)
        self.assertIn('--confirm-atomic-events', help_result.stdout)

    def test_cli_matches_core_all_states(self):
        for data, confirm, state in ((CSV, True, 'Ready'),
                                     (CSV.replace(b',2\n', b',3\n'), True, 'Failed'),
                                     (CSV, False, 'Unknown')):
            with self.subTest(state=state):
                self.billed.write_bytes(data)
                out = self.work / (state + '.json')
                args = [self.usage, self.billed, '--out', out]
                if confirm:
                    args.append('--confirm-atomic-events')
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['state'], state)
                self.assertEqual(json.loads(out.read_text()), reconcile(CSV, data, confirm))

    def test_missing_file_is_error(self):
        result = self.run_cli(self.work / 'absent.csv', self.billed, '--out', self.output)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)['state'], 'Unknown')
        self.assertFalse(self.output.exists())

    def test_existing_output_is_preserved(self):
        self.output.write_text('retain this evidence')
        result = self.run_cli(self.usage, self.billed, '--out', self.output)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)['error'], 'FileExistsError')
        self.assertEqual(self.output.read_text(), 'retain this evidence')

    def test_bad_arguments(self):
        self.assertEqual(self.run_cli().returncode, 2)

    def test_bounded_read_of_oversized_file(self):
        self.billed.write_bytes(b'x' * (MAX_FILE_BYTES + 100))
        result = self.run_cli(self.usage, self.billed, '--out', self.output, '--confirm-atomic-events')
        self.assertEqual(result.returncode, 0)
        report = json.loads(self.output.read_text())
        self.assertEqual(report['state'], 'Unknown')
        self.assertEqual(report['inputs']['billed']['observed_bytes'], MAX_FILE_BYTES + 1)
        self.assertIsNone(report['inputs']['billed']['sha256'])


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def payload(self, data=CSV, confirm=True):
        return {'usage_csv_base64': base64.b64encode(CSV).decode(),
                'billed_csv_base64': base64.b64encode(data).decode(),
                'confirm_atomic_events': confirm}

    def request(self, payload=None, *, body=None, path='/check', method='POST', headers=None):
        if body is None:
            body = json.dumps(self.payload() if payload is None else payload).encode()
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            connection.request(method, path, body, headers if headers is not None else {'Content-Type': 'application/json'})
            response = connection.getresponse()
            return response.status, response.read(), response.getheader('Content-Type')
        finally:
            connection.close()

    def assert_error(self, expected_status, expected_code, **kwargs):
        status, body, content_type = self.request(**kwargs)
        self.assertEqual(status, expected_status)
        self.assertIn('application/json', content_type)
        self.assertEqual(json.loads(body), {'error': expected_code, 'state': 'Unknown'})

    def test_api_matches_core_all_states_without_origin(self):
        for data, confirm, state in ((CSV, True, 'Ready'),
                                     (CSV.replace(b',2\n', b',3\n'), True, 'Failed'),
                                     (CSV, False, 'Unknown'), (b'bad header', True, 'Unknown')):
            with self.subTest(state=state, data=data):
                status, body, _ = self.request(self.payload(data, confirm))
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body), reconcile(CSV, data, confirm))
                self.assertEqual(json.loads(body)['state'], state)

    def test_same_origin_allowed(self):
        status, _, _ = self.request(headers={'Content-Type': 'application/json',
                                             'Origin': f'http://127.0.0.1:{self.server.server_port}'})
        self.assertEqual(status, 200)

    def test_cross_origin_and_host_rejected(self):
        for header in ({'Origin': 'https://example.invalid'}, {'Origin': 'null'}, {'Host': 'example.invalid'}):
            with self.subTest(header=header):
                self.assert_error(403, 'ORIGIN_OR_HOST_REJECTED', headers={'Content-Type': 'application/json', **header})

    def test_request_shape(self):
        for payload in ([], None, {'extra': 1}, {**self.payload(), 'extra': 1},
                        {**self.payload(), 'confirm_atomic_events': 1},
                        {**self.payload(), 'usage_csv_base64': 5}):
            with self.subTest(payload=payload):
                self.assert_error(400, 'INVALID_REQUEST', body=json.dumps(payload).encode())

    def test_invalid_json_base64_duplicate_keys(self):
        for body in (b'{', b'{"a":1,"a":2}', b'\xff',
                     json.dumps({**self.payload(), 'usage_csv_base64': '!'}).encode()):
            with self.subTest(body=body):
                self.assert_error(400, 'INVALID_JSON_OR_BASE64', body=body)

    def test_content_type(self):
        self.assert_error(415, 'JSON_REQUIRED', headers={'Content-Type': 'text/plain'})

    def test_body_size_and_transfer_encoding(self):
        self.assert_error(413, 'BODY_TOO_LARGE_OR_EMPTY', body=b'')
        self.assert_error(413, 'BODY_TOO_LARGE_OR_EMPTY', headers={'Content-Type': 'application/json', 'Content-Length': str(MAX_BODY_BYTES + 1)})
        self.assert_error(400, 'TRANSFER_ENCODING_UNSUPPORTED', headers={'Transfer-Encoding': 'chunked'})
        self.assert_error(411, 'CONTENT_LENGTH_REQUIRED', headers={'Content-Length': '-1'})

    def test_unknown_routes(self):
        self.assert_error(404, 'NOT_FOUND', path='/missing')
        self.assert_error(404, 'NOT_FOUND', path='/missing', method='GET')

    def test_packaged_web_assets_and_samples(self):
        for path, kind in (('/', 'text/html'), ('/app.js', 'text/javascript'), ('/style.css', 'text/css')):
            with self.subTest(path=path):
                status, body, content_type = self.request(method='GET', path=path)
                self.assertEqual(status, 200)
                self.assertIn(kind, content_type)
                self.assertTrue(body)
        for name, state in (('clean', 'Ready'), ('dirty', 'Failed'), ('unknown', 'Unknown')):
            with self.subTest(sample=name):
                status, body, _ = self.request(method='GET', path='/sample/' + name)
                self.assertEqual(status, 200)
                sample = json.loads(body)
                payload = {key: sample[key] for key in self.payload()}
                status, body, _ = self.request(payload)
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body)['state'], state)


if __name__ == '__main__':
    unittest.main()
