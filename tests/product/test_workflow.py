"""Workflow adapters: explicit oracles for success, failure, unknown and repeats."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from truquence.workflow import accept, skeleton, workflow_identity


def workflow():
    return {'nodes': [{'id': 'one', 'name': 'Result', 'type': 'n8n-nodes-base.set',
                       'typeVersion': 3.4, 'parameters': {}, 'position': [0, 0]}],
            'connections': {}, 'settings': {}}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix='truquence-workflow-'))
        self.contract_path = self.work / 'contract.json'
        self.execution_path = self.work / 'execution.json'
        self.workflow = workflow()
        self.contract = skeleton(self.workflow)
        self.contract['x-checks'][0]['x-expect_items'] = [{'quantity': 7}]
        self.execution = {'finished': True, 'status': 'success', 'workflowData': copy.deepcopy(self.workflow),
                          'data': {'resultData': {'runData': {'Result': [
                              {'data': {'main': [[{'json': {'quantity': 7}}]]}, 'executionStatus': 'success'}]}}}}
        self.make_contract = {'x-schema': 'truquence.workflow-contract.v0.2', 'x-source': 'make',
                              'x-scope': 'execution_observation', 'x-scenario_id': 1229,
                              'x-execution_id': 'run-1', 'x-expect_operations': 10}
        # Shape and status/imtId semantics from Make's public scenario-log documentation.
        self.make_row = {'id': 'run-1', 'imtId': '1632371744497_scenario.1229.auto.run-1',
                         'type': 'auto', 'status': 1, 'operations': 10}
        self.command = str(Path(sys.executable).with_name('truquence'))

    def report(self, contract=None, execution=None, source='n8n'):
        self.contract_path.write_text(json.dumps(self.contract if contract is None else contract))
        self.execution_path.write_text(json.dumps(self.execution if execution is None else execution))
        return accept(self.contract_path, self.execution_path, source)

    def check_execution(self, expected, mutate):
        doc = copy.deepcopy(self.execution)
        mutate(doc)
        self.assertEqual(self.report(execution=doc)['status'], expected)

    def test_pass_and_exact_byte_fingerprints(self):
        report = self.report()
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(report['business_acceptance'], 'UNKNOWN')
        self.assertEqual(report['scope'], 'execution_observation')
        self.assertEqual(report['inputs']['execution']['sha256'], hashlib.sha256(self.execution_path.read_bytes()).hexdigest())
        self.assertEqual(report['counts'], {'PASS': 3, 'FAIL': 0, 'UNKNOWN': 0})

    def test_draft_never_passes_then_independent_expectation_passes(self):
        self.assertEqual(self.report(contract=skeleton(self.workflow))['status'], 'UNKNOWN')
        self.assertEqual(self.report()['status'], 'PASS')

    def test_wrong_value_duplicate_item_missing_item_and_type_fail(self):
        for items in ([{'quantity': 8}], [{'quantity': 7}, {'quantity': 7}], [], [{'quantity': True}], [{'quantity': '7'}]):
            with self.subTest(items=items):
                doc = copy.deepcopy(self.execution)
                doc['data']['resultData']['runData']['Result'][0]['data']['main'][0] = [{'json': i} for i in items]
                self.assertEqual(self.report(execution=doc)['status'], 'FAIL')

    def test_empty_output_requires_explicit_empty_expectation(self):
        self.contract['x-checks'][0]['x-expect_items'] = []
        self.execution['data']['resultData']['runData']['Result'][0]['data']['main'] = [[]]
        self.assertEqual(self.report()['status'], 'PASS')

    def test_repeated_run_fails_then_explicit_repeated_oracle_passes(self):
        runs = self.execution['data']['resultData']['runData']['Result']
        runs.append(copy.deepcopy(runs[0]))
        self.assertEqual(self.report()['status'], 'FAIL')
        self.contract['x-checks'][0]['x-expect_runs'] = 2
        self.contract['x-checks'][0]['x-expect_items'] *= 2
        self.assertEqual(self.report()['status'], 'PASS')

    def test_missing_node_and_incomplete_data_unknown(self):
        self.check_execution('UNKNOWN', lambda d: d['data']['resultData']['runData'].clear())
        self.check_execution('UNKNOWN', lambda d: d.pop('workflowData'))
        self.check_execution('UNKNOWN', lambda d: d['data']['resultData'].pop('runData'))
        for value in (None, [], {'data': None}, {'data': {'resultData': None}}, {'workflowData': {}}):
            with self.subTest(value=value):
                self.assertEqual(self.report(execution=value if value is not None else [])['status'], 'UNKNOWN')

    def test_unfinished_waiting_unknown_status_not_pass(self):
        for status in ('running', 'waiting', 'new', 'unknown', True):
            with self.subTest(status=status):
                self.check_execution('UNKNOWN', lambda d: d.update(status=status))
        for finished in (False, None, 1, 'true'):
            with self.subTest(finished=finished):
                self.check_execution('UNKNOWN', lambda d: d.update(finished=finished))

    def test_node_unknown_status_cannot_pass(self):
        for state in ('running', 'waiting', 'canceled', 'unsupported'):
            self.check_execution('UNKNOWN', lambda d: d['data']['resultData']['runData']['Result'][0].update(executionStatus=state))

    def test_different_workflow_id_cannot_pass(self):
        self.check_execution('FAIL', lambda d: d['workflowData'].update(id='other'))

    def test_old_cli_finished_without_status_supported(self):
        self.check_execution('PASS', lambda d: d.pop('status'))

    def test_errors_never_pass_even_with_finished_true(self):
        for status in ('error', 'crashed', 'canceled'):
            with self.subTest(status=status):
                self.check_execution('FAIL', lambda d: d.update(status=status))
        self.check_execution('FAIL', lambda d: d['data']['resultData'].update(error={'message': 'failed'}))
        self.check_execution('FAIL', lambda d: d['data']['resultData']['runData']['Result'][0].update(error={'message': 'continued error'}))
        self.check_execution('FAIL', lambda d: d['data']['resultData']['runData']['Result'][0].update(executionStatus='error'))
        self.check_execution('FAIL', lambda d: d['data']['resultData']['runData'].update(Unmapped=[{'error': {'message': 'failed'}}]))

    def test_runtime_workflow_drift_fails_editor_move_passes(self):
        self.check_execution('FAIL', lambda d: d['workflowData']['nodes'][0]['parameters'].update(value=8))
        self.check_execution('PASS', lambda d: d['workflowData']['nodes'][0].update(position=[10, 20], notes='moved'))
        self.check_execution('FAIL', lambda d: d['workflowData']['settings'].update(executionOrder='v1'))

    def test_coverage_cannot_be_silently_reduced(self):
        self.workflow['nodes'].append({'id': 'two', 'name': 'Omitted', 'type': 'test', 'parameters': {}})
        self.contract['x-workflow_sha256'] = workflow_identity(self.workflow)
        self.execution['workflowData'] = self.workflow
        self.assertEqual(self.report()['status'], 'UNKNOWN')

    def test_binary_multibranch_missing_json_unknown(self):
        for branches in ([], [[], []], [[{'binary': {}, 'json': {'quantity': 7}}]], [[{'json': None}]], None):
            with self.subTest(branches=branches):
                self.check_execution('UNKNOWN', lambda d: d['data']['resultData']['runData']['Result'][0]['data'].update(main=branches))

    def test_invalid_contract_duplicate_checks_unknown(self):
        for change in (lambda c: c.update(extra=True),
                       lambda c: c.update(**{'x-checks': []}),
                       lambda c: c.update(**{'x-source': 'make'}),
                       lambda c: c['x-checks'].append(copy.deepcopy(c['x-checks'][0])),
                       lambda c: c['x-checks'][0].update(**{'x-expect_runs': True}),
                       lambda c: c['x-checks'][0].update(**{'x-expect_items': 'anything'})):
            contract = copy.deepcopy(self.contract)
            change(contract)
            self.assertEqual(self.report(contract=contract)['status'], 'UNKNOWN')

    def test_bad_json_duplicate_keys_and_nonfinite_unknown(self):
        self.report()
        for raw in (b'{', b'\xff', b'{"status":1,"status":3}', b'{"n":NaN}', b''):
            with self.subTest(raw=raw):
                self.execution_path.write_bytes(raw)
                self.assertEqual(accept(self.contract_path, self.execution_path, 'n8n')['status'], 'UNKNOWN')
        self.assertEqual(accept(self.contract_path, self.work / 'missing.json', 'n8n')['status'], 'UNKNOWN')

    def test_make_public_format_envelopes(self):
        for doc in (self.make_row, {'scenarioLog': self.make_row}, {'scenarioLogs': [self.make_row]}):
            with self.subTest(doc=doc):
                report = self.report(self.make_contract, doc, 'make')
                self.assertEqual(report['status'], 'PASS')
                self.assertEqual(report['business_acceptance'], 'UNKNOWN')

    def test_make_warn_pause_error_unknown_and_error(self):
        for updates, expected in (({'status': 2}, 'UNKNOWN'), ({'status': 3}, 'FAIL'),
                                  ({'status': True}, 'UNKNOWN'), ({'status': '1'}, 'UNKNOWN'),
                                  ({'status': 9}, 'UNKNOWN'), ({'eventType': 'EXECUTION_PAUSED'}, 'UNKNOWN'),
                                  ({'type': 'modify'}, 'UNKNOWN'), ({'error': {'message': 'failed'}}, 'FAIL')):
            with self.subTest(updates=updates):
                self.assertEqual(self.report(self.make_contract, {**self.make_row, **updates}, 'make')['status'], expected)

    def test_make_missing_status_operations_and_identity_unknown(self):
        for key in ('status', 'operations', 'imtId', 'id', 'type'):
            with self.subTest(key=key):
                row = self.make_row.copy()
                row.pop(key)
                self.assertEqual(self.report(self.make_contract, row, 'make')['status'], 'UNKNOWN')

    def test_make_wrong_scenario_operations_and_boolean_not_pass(self):
        for updates, expected in (({'scenarioId': 555}, 'FAIL'), ({'operations': 9}, 'FAIL'),
                                  ({'operations': True}, 'UNKNOWN'), ({'scenarioId': True}, 'FAIL')):
            with self.subTest(updates=updates):
                self.assertEqual(self.report(self.make_contract, {**self.make_row, **updates}, 'make')['status'], expected)

    def test_make_explicit_selection_no_duplicates_or_missing(self):
        for rows, expected in (([self.make_row, self.make_row], 'UNKNOWN'), ([], 'UNKNOWN'),
                               ([{**self.make_row, 'id': 'other'}, self.make_row], 'PASS')):
            with self.subTest(rows=rows):
                self.assertEqual(self.report(self.make_contract, {'scenarioLogs': rows}, 'make')['status'], expected)

    def test_init_workflow_validation(self):
        for doc in ({}, [], {'nodes': []}, {'nodes': [1], 'connections': {}},
                    {**self.workflow, 'nodes': self.workflow['nodes'] * 2}):
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                skeleton(doc)

    def cli(self, *args):
        return subprocess.run([self.command, *map(str, args)], cwd=self.work,
                              capture_output=True, text=True, timeout=15)

    def test_installed_init_and_accept_all_states_and_no_overwrite(self):
        self.report()
        wf = self.work / 'workflow.json'
        wf.write_text(json.dumps(self.workflow))
        draft = self.work / 'draft.json'
        created = self.cli('init', '--workflow', wf, '--out', draft)
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertEqual(json.loads(created.stdout)['status'], 'UNKNOWN')
        first = draft.read_bytes()
        self.assertEqual(self.cli('init', '--workflow', wf, '--out', draft).returncode, 3)
        self.assertEqual(draft.read_bytes(), first)
        for label, contract, code in (('pass', self.contract, 0), ('unknown', skeleton(self.workflow), 2),
                                     ('fail', {**self.contract, 'x-workflow_sha256': '0' * 64}, 1)):
            self.report(contract=contract)
            prefix = self.work / label
            args = ('accept', '--format', 'n8n', '--contract', self.contract_path,
                    '--execution', self.execution_path, '--out', prefix)
            result = self.cli(*args)
            self.assertEqual(result.returncode, code, result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], label.upper())
            output = prefix.with_suffix('.json').read_bytes()
            self.assertIn(label.upper(), prefix.with_suffix('.md').read_text())
            self.assertEqual(self.cli(*args).returncode, 3)
            self.assertEqual(prefix.with_suffix('.json').read_bytes(), output)

    def test_cli_make_failure_missing_input_and_partial_output(self):
        self.report(self.make_contract, {**self.make_row, 'status': 3}, 'make')
        args = ['accept', '--format=make', '--contract', self.contract_path, '--execution', self.execution_path]
        result = self.cli(*args, '--out', self.work / 'make')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.execution_path = self.work / 'absent.json'
        self.assertEqual(self.cli(*args[:4], '--execution', self.execution_path, '--out', self.work / 'missing').returncode, 2)
        prefix = self.work / 'partial'
        prefix.with_suffix('.md').write_text('preserve')
        self.assertEqual(self.cli(*args, '--out', prefix).returncode, 3)
        self.assertEqual(prefix.with_suffix('.md').read_text(), 'preserve')


if __name__ == '__main__':
    unittest.main()
