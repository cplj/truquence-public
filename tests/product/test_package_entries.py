"""Installed distribution entrypoints and MCP contract boundary."""
import unittest


class PackageEntries(unittest.TestCase):
    def test_recorder_has_a_dedicated_namespace_and_commands(self):
        import importlib.metadata
        import truquence_recorder
        self.assertIn('truquence_recorder', truquence_recorder.__file__)
        self.assertEqual(truquence_recorder.__version__, '0.3.0')
        names = {e.name for e in importlib.metadata.distribution('truquence').entry_points if e.group == 'console_scripts'}
        self.assertEqual(names, {'truquence', 'truquence-mcp', 'truquence-recorder'})

    def test_mcp_accepts_supplied_execution(self):
        from truquence.mcp_server import truquence_accept
        contract = '{"x-schema":"truquence.workflow-contract.v0.2","x-source":"make","x-scope":"execution_observation","x-scenario_id":1229,"x-execution_id":"run-1","x-expect_operations":10}'
        execution = '{"id":"run-1","imtId":"1632371744497_scenario.1229.auto.run-1","type":"auto","status":1,"operations":10}'
        result = truquence_accept(contract, execution, 'make')
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['report']['business_acceptance'], 'UNKNOWN')
        self.assertEqual(result['gateBlocked'], result['status'] != 'PASS')


if __name__ == '__main__':
    unittest.main()
