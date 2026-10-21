"""Generated properties at the public capture and MCP input boundaries."""
import json
import unittest
from hypothesis import given, seed, settings, strategies as st
from signwarden_recorder.core import canonical, parse
from truquence.mcp_server import truquence_accept

scalar = st.none() | st.booleans() | st.integers(min_value=-2**63, max_value=2**63) | st.text(max_size=30)
values = st.recursive(scalar, lambda child: st.lists(child, max_size=8) |
                      st.dictionaries(st.text(max_size=20), child, max_size=8), max_leaves=40)


class CaptureProperties(unittest.TestCase):
    @seed(20261021)
    @settings(max_examples=200, deadline=None, database=None)
    @given(values)
    def test_capture_roundtrip(self, value):
        self.assertEqual(parse(canonical(value)), value)

    @seed(20261021)
    @settings(max_examples=200, deadline=None, database=None)
    @given(st.text(max_size=20), values, values)
    def test_both_boundaries_reject_duplicate_keys(self, key, first, second):
        text = '{' + json.dumps(key) + ':' + json.dumps(first) + ',' + json.dumps(key) + ':' + json.dumps(second) + '}'
        with self.assertRaises(ValueError):
            parse(text.encode())
        with self.assertRaises(ValueError):
            truquence_accept('{}', text)

    @seed(20261021)
    @settings(max_examples=200, deadline=None, database=None)
    @given(st.binary(max_size=4096))
    def test_capture_binary_input_has_documented_errors(self, raw):
        try:
            result = parse(raw)
        except ValueError:
            return
        self.assertEqual(parse(canonical(result)), result)

    def test_both_boundaries_reject_oversize_and_depth(self):
        for raw in (b' ' * (1048576 + 1), b'[' * 1100 + b'0' + b']' * 1100):
            with self.assertRaises(ValueError):
                parse(raw)
            with self.assertRaises(ValueError):
                truquence_accept('{}', raw.decode())


if __name__ == '__main__':
    unittest.main()
