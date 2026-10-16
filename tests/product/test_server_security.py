"""Real-socket regressions for bounded local HTTP request handling."""
import http.client
import json
import socket
import threading
import time
import unittest
from unittest import mock

from truquence.server import Handler, HTTPServer


class SmallServer(HTTPServer):
    max_connections = 2
    header_timeout = 0.3
    body_timeout = 0.3


class ServerSecurityTests(unittest.TestCase):
    def setUp(self):
        self.started = threading.Condition()
        self.connections = 0
        owner = self

        class ObservedHandler(Handler):
            def setup(self):
                super().setup()
                with owner.started:
                    owner.connections += 1
                    owner.started.notify_all()

        self.server = SmallServer(('127.0.0.1', 0), ObservedHandler)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()
        self.sockets = []

    def tearDown(self):
        for connection in self.sockets:
            connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())

    def connect(self):
        connection = socket.create_connection(self.server.server_address, timeout=1)
        connection.settimeout(1)
        self.sockets.append(connection)
        return connection

    def wait_started(self, expected):
        with self.started:
            self.assertTrue(self.started.wait_for(lambda: self.connections >= expected, timeout=1))

    def get(self, **headers):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=0.8)
        try:
            connection.request('GET', '/sample/clean', headers=headers)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def body_headers(self):
        return (f'POST /check HTTP/1.1\r\nHost: 127.0.0.1:{self.server.server_port}\r\n'
                'Content-Type: application/json\r\nContent-Length: 100\r\n\r\n').encode()

    def read_all(self, connection):
        chunks = []
        while True:
            try:
                chunk = connection.recv(4096)
            except ConnectionResetError:
                return b''.join(chunks)
            if not chunk:
                return b''.join(chunks)
            chunks.append(chunk)

    def assert_recovers(self):
        deadline = time.monotonic() + 1
        while True:
            status, body = self.get()
            if status != 503 or time.monotonic() >= deadline:
                break
            time.sleep(0.01)
        self.assertEqual(status, 200, body)
        self.assertIn('usage_csv_base64', json.loads(body))

    def test_slow_header_isolated_and_expires(self):
        connection = self.connect()
        connection.sendall(b'GET / HTTP/1.1\r\nHost: ')
        self.wait_started(1)
        self.assertEqual(self.get()[0], 200)
        started = time.monotonic()
        self.assertEqual(self.read_all(connection), b'')
        self.assertLess(time.monotonic() - started, 0.8)
        self.assert_recovers()

    def test_slow_body_isolated_and_returns_timeout(self):
        connection = self.connect()
        connection.sendall(self.body_headers() + b'{')
        self.wait_started(1)
        self.assertEqual(self.get()[0], 200)
        response = self.read_all(connection)
        self.assertIn(b' 408 ', response)
        self.assertIn(b'"REQUEST_TIMEOUT"', response)
        self.assert_recovers()

    def assert_drip_deadline(self, prefix, drip, expected):
        connection = self.connect()
        connection.sendall(prefix)
        self.wait_started(1)
        stopped = threading.Event()

        def feed():
            while not stopped.wait(0.04):
                try:
                    connection.sendall(drip)
                except OSError:
                    break

        thread = threading.Thread(target=feed, daemon=True)
        started = time.monotonic()
        thread.start()
        try:
            response = self.read_all(connection)
        finally:
            stopped.set()
            thread.join(timeout=1)
        elapsed = time.monotonic() - started
        self.assertGreater(elapsed, 0.15)
        self.assertLess(elapsed, 0.8)
        self.assertIn(expected, response)
        self.assert_recovers()

    def test_drip_header_cannot_refresh_total_deadline(self):
        self.assert_drip_deadline(b'GET / HTTP/1.1\r\nX-Slow: ', b'x', b'')

    def test_drip_body_cannot_refresh_total_deadline(self):
        self.assert_drip_deadline(self.body_headers() + b'{', b' ', b' 408 ')

    def test_connection_limit_rejects_excess_and_recovers(self):
        for expected in (1, 2):
            self.connect().sendall(b'GET / HTTP/1.1\r\nX-Slow: ')
            self.wait_started(expected)
        connection = self.connect()
        response = self.read_all(connection)
        self.assertIn(b' 503 ', response)
        self.assertIn(b'"SERVER_BUSY"', response)
        self.assertEqual(self.connections, 2)
        for connection in self.sockets[:2]:
            self.assertEqual(self.read_all(connection), b'')
        self.assert_recovers()

    def test_host_and_origin_guards_remain_enforced(self):
        self.assertEqual(self.get(Host='example.invalid')[0], 403)
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=1)
        try:
            connection.request('POST', '/check', b'{}',
                               {'Content-Type': 'application/json', 'Origin': 'https://example.invalid'})
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            self.assertEqual(json.loads(response.read())['error'], 'ORIGIN_OR_HOST_REJECTED')
        finally:
            connection.close()
        self.assert_recovers()

    def test_memory_pressure_returns_explicit_unknown_and_recovers(self):
        body = b'{"usage_csv_base64":"YQ==","billed_csv_base64":"YQ==","confirm_atomic_events":true}'
        for target in ('json.loads', 'base64.b64decode', 'reconcile', 'json.dumps'):
            with self.subTest(target=target):
                connection = http.client.HTTPConnection(*self.server.server_address, timeout=1)
                try:
                    with mock.patch('truquence.server.' + target, side_effect=MemoryError):
                        connection.request('POST', '/check', body, {'Content-Type': 'application/json'})
                        response = connection.getresponse()
                        status, received = response.status, response.read()
                    self.assertEqual(status, 503)
                    self.assertEqual(json.loads(received),
                                     {'error': 'INPUT_RESOURCE_LIMIT', 'state': 'Unknown'})
                finally:
                    connection.close()
                self.assert_recovers()


if __name__ == '__main__':
    unittest.main()
