"""Offline acceptance of supplied n8n executions and Make scenario logs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from actioncontract import MAX_INPUT_BYTES, check_limits, decode, read_bytes

SCHEMA = 'truquence.workflow-contract.v0.2'
LIMIT = MAX_INPUT_BYTES
STATES = {'PASS': 'Ready', 'FAIL': 'Failed', 'UNKNOWN': 'Unknown'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False)


def read(path):
    raw = read_bytes(path)
    if not raw or len(raw) > LIMIT:
        raise ValueError('JSON file must contain 1 byte to 1 MiB')
    return decode(raw), {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def workflow_identity(workflow):
    check_limits(workflow)
    if not isinstance(workflow, dict) or not isinstance(workflow.get('nodes'), list) or not workflow['nodes']:
        raise ValueError('Expected one n8n workflow object with nodes')
    nodes = workflow['nodes']
    for field in ('name', 'id'):
        values = [n.get(field) if isinstance(n, dict) else None for n in nodes]
        if any(not isinstance(v, str) or not v.strip() for v in values) or len(set(values)) != len(values):
            raise ValueError('Missing or duplicate node ' + field)
    if any(not isinstance(n.get('type'), str) or not isinstance(n.get('parameters'), dict) for n in nodes):
        raise ValueError('Node type and parameters are required')
    if not isinstance(workflow.get('connections'), dict):
        raise ValueError('Workflow connections are required')
    # Ignore editor coordinates and server metadata, preserve execution configuration.
    ignored = {'position', 'notes', 'notesInFlow', 'color'}
    identity = {'id': workflow.get('id'), 'nodes': sorted([{k: v for k, v in n.items() if k not in ignored} for n in nodes], key=lambda n: n['id']),
                'connections': workflow['connections'], 'settings': workflow.get('settings', {})}
    return hashlib.sha256(canonical(identity).encode()).hexdigest()


def skeleton(workflow):
    return {'x-schema': SCHEMA, 'x-source': 'n8n', 'x-scope': 'execution_observation',
            'x-workflow_sha256': workflow_identity(workflow),
            'x-checks': [{'x-node': n['name'], 'x-expect_runs': 1, 'x-expect_items': None}
                         for n in workflow['nodes'] if n.get('disabled') is not True]}


def validate(contract, source):
    check_limits(contract)
    if not isinstance(contract, dict) or contract.get('x-schema') != SCHEMA or contract.get('x-source') != source:
        raise ValueError('Expected a v0.2 workflow contract matching --format')
    if contract.get('x-scope') != 'execution_observation':
        raise ValueError('Only execution_observation scope is supported')
    common = {'x-schema', 'x-source', 'x-scope'}
    if source == 'n8n':
        if set(contract) != common | {'x-workflow_sha256', 'x-checks'}:
            raise ValueError('Unsupported or missing n8n contract fields')
        if not isinstance(contract['x-workflow_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', contract['x-workflow_sha256']):
            raise ValueError('Expected workflow SHA-256')
        checks = contract['x-checks']
        if not isinstance(checks, list) or not checks:
            raise ValueError('At least one output check is required')
        names = []
        for check in checks:
            if not isinstance(check, dict) or set(check) != {'x-node', 'x-expect_runs', 'x-expect_items'}:
                raise ValueError('Expected node, run count and exact output items')
            name = check['x-node']
            if not isinstance(name, str) or not name.strip() or name in names:
                raise ValueError('Missing or duplicate checked node')
            names.append(name)
            if type(check['x-expect_runs']) is not int or check['x-expect_runs'] < 1:
                raise ValueError('Expected positive integer run count')
            items = check['x-expect_items']
            if items is not None and (not isinstance(items, list) or any(not isinstance(i, dict) for i in items)):
                raise ValueError('Expected a list of JSON output objects or null for a draft')
    else:
        if set(contract) != common | {'x-scenario_id', 'x-execution_id', 'x-expect_operations'}:
            raise ValueError('Expected scenario ID, execution ID and operation count')
        if type(contract['x-scenario_id']) is not int or contract['x-scenario_id'] < 1:
            raise ValueError('Expected positive integer scenario ID')
        if not isinstance(contract['x-execution_id'], str) or not contract['x-execution_id'].strip():
            raise ValueError('Expected execution ID')
        if type(contract['x-expect_operations']) is not int or contract['x-expect_operations'] < 1:
            raise ValueError('Expected positive integer operation count')


def n8n(execution, contract):
    checks = []

    def add(name, status, reason):
        checks.append({'id': name, 'status': status, 'reason': reason})

    if not isinstance(execution, dict):
        raise ValueError('Expected one n8n execution object, not a list or console transcript')
    result = execution.get('data', {}).get('resultData', {})
    if not isinstance(result, dict):
        raise ValueError('Missing n8n resultData')
    run_data = result.get('runData')
    if not isinstance(run_data, dict):
        raise ValueError('Missing n8n runData; export full execution data')
    status = execution.get('status')
    has_error = bool(result.get('error')) or any(
        isinstance(runs, list) and any(isinstance(r, dict) and
                                     (r.get('error') or r.get('executionStatus') == 'error') for r in runs)
        for runs in run_data.values())
    if status in ('error', 'crashed', 'canceled') or has_error:
        add('execution', 'FAIL', 'Execution or node reported an error; no automatic retry.')
    elif execution.get('finished') is True and status in (None, 'success'):
        add('execution', 'PASS', 'Execution has a terminal success marker.')
    else:
        add('execution', 'UNKNOWN', 'Execution is unfinished, interrupted or has unsupported status.')
    workflow = execution.get('workflowData')
    if not isinstance(workflow, dict):
        add('workflow', 'UNKNOWN', 'Workflow snapshot missing; cannot bind execution to the contract.')
    elif workflow_identity(workflow) != contract['x-workflow_sha256']:
        add('workflow', 'FAIL', 'Workflow execution configuration differs from the contract.')
    else:
        add('workflow', 'PASS', 'Execution snapshot matches the pinned workflow configuration.')
    expected_names = {c['x-node'] for c in contract['x-checks']}
    if isinstance(workflow, dict):
        active = {n['name'] for n in workflow['nodes'] if n.get('disabled') is not True}
        if expected_names != active or set(run_data) - active:
            add('coverage', 'UNKNOWN', 'Contract must cover every enabled node; no unmapped execution nodes allowed.')
    for check in contract['x-checks']:
        name = check['x-node']
        runs = run_data.get(name)
        if not isinstance(runs, list) or not runs:
            add(name, 'UNKNOWN', 'Node execution evidence is missing.')
            continue
        if len(runs) != check['x-expect_runs']:
            add(name, 'FAIL', 'Observed run count differs from expected; check repeats or missing runs.')
            continue
        observed = []
        for run in runs:
            if not isinstance(run, dict):
                raise ValueError('Invalid node run')
            if run.get('executionStatus') not in (None, 'success', 'error'):
                add(name, 'UNKNOWN', 'Node run has an unfinished or unsupported execution status.')
                break
            branches = run.get('data', {}).get('main')
            if not isinstance(branches, list) or len(branches) != 1 or not isinstance(branches[0], list):
                add(name, 'UNKNOWN', 'Expected one main output branch; missing or multi-branch output requires review.')
                break
            if any(not isinstance(i, dict) or not isinstance(i.get('json'), dict) or 'binary' in i for i in branches[0]):
                add(name, 'UNKNOWN', 'Only JSON output items are supported; binary or malformed items require review.')
                break
            observed.extend(i['json'] for i in branches[0])
        else:
            expected = check['x-expect_items']
            if expected is None:
                add(name, 'UNKNOWN', 'Draft contract: set expected output independently before acceptance.')
            elif canonical(observed) != canonical(expected):
                add(name, 'FAIL', 'Exact JSON output items differ from expected (including item count and order).')
            else:
                add(name, 'PASS', 'Run count and exact JSON output items match.')
    return checks


def make(document, contract):
    if not isinstance(document, dict):
        raise ValueError('Expected Make scenarioLog or scenarioLogs object')
    rows = document.get('scenarioLogs') if 'scenarioLogs' in document else [document.get('scenarioLog', document)]
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise ValueError('Invalid Make scenario logs')
    selected = [r for r in rows if r.get('id') == contract['x-execution_id']]
    if len(selected) != 1:
        return [{'id': 'execution', 'status': 'UNKNOWN', 'reason': 'Expected exactly one matching execution ID; missing or duplicate records.'}]
    row = selected[0]
    checks = []

    def add(name, status, reason):
        checks.append({'id': name, 'status': status, 'reason': reason})

    marker = re.search(r'_scenario\.(\d+)\.', str(row.get('imtId', '')))
    scenario = row.get('scenarioId', int(marker[1]) if marker else None)
    if scenario is None:
        add('scenario', 'UNKNOWN', 'No scenario identity in log; cannot bind it to the contract.')
    elif type(scenario) is not int or scenario != contract['x-scenario_id'] or (marker and int(marker[1]) != scenario):
        add('scenario', 'FAIL', 'Scenario identity differs from the contract or contradicts imtId.')
    else:
        add('scenario', 'PASS', 'Scenario and execution identity match.')
    status = row.get('status')
    if row.get('error') or type(status) is int and status == 3:
        add('execution', 'FAIL', 'Make reports an execution error; no automatic retry.')
    elif row.get('eventType') == 'EXECUTION_PAUSED' or row.get('type') not in ('auto', 'manual', 'instant'):
        add('execution', 'UNKNOWN', 'Paused execution or unsupported log type; not a completed run.')
    elif type(status) is int and status == 1:
        add('execution', 'PASS', 'Make reports execution success (status 1).')
    else:
        add('execution', 'UNKNOWN', 'Warning, missing or unsupported execution status requires review.')
    operations = row.get('operations')
    if type(operations) is not int or operations < 0:
        add('operations', 'UNKNOWN', 'Operation count is missing or invalid.')
    elif operations != contract['x-expect_operations']:
        add('operations', 'FAIL', 'Operation count differs from expected.')
    else:
        add('operations', 'PASS', 'Operation count matches; this does not verify business effects or outputs.')
    return checks


def accept(contract_path, execution_path, source):
    inputs, checks = {}, []
    try:
        contract, inputs['contract'] = read(contract_path)
        execution, inputs['execution'] = read(execution_path)
        validate(contract, source)
        checks = (n8n if source == 'n8n' else make)(execution, contract)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, MemoryError) as error:
        checks.append({'id': 'input', 'status': 'UNKNOWN',
                       'reason': 'INPUT_RESOURCE_LIMIT: insufficient memory' if isinstance(error, MemoryError) else str(error)})
    statuses = [c['status'] for c in checks]
    status = 'FAIL' if 'FAIL' in statuses else 'UNKNOWN' if not statuses or 'UNKNOWN' in statuses else 'PASS'
    return {'policy_version': 'workflow-v0.2', 'status': status, 'state': STATES[status],
            'source': source, 'scope': 'execution_observation',
            'limitations': 'Supplied logs only; unsigned. No authorization, durable external effects, source completeness, retry permission or business acceptance is verified.',
            'business_acceptance': 'UNKNOWN', 'inputs': inputs,
            'counts': {s: statuses.count(s) for s in STATES}, 'checks': checks}


def markdown(report):
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')
    lines = ['# Workflow acceptance report', '', '**' + report['status'] + '** — execution observation only.', '',
             report['limitations'], '', 'Business acceptance: UNKNOWN. FAIL and UNKNOWN block this acceptance scope.', '',
             '| Check | Decision | Evidence / next step |', '|---|---|---|']
    lines += ['| ' + ' | '.join(cell(c[k]) for k in ('id', 'status', 'reason')) + ' |' for c in report['checks']]
    lines += ['', 'Input SHA-256 fingerprints (exact bytes; integrity only):', '']
    lines += ['- ' + name + ': `' + item['sha256'] + '`' for name, item in report['inputs'].items()]
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(prog='truquence')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='create a draft contract from one n8n workflow JSON')
    init.add_argument('--workflow', required=True)
    init.add_argument('--out', required=True)
    command = commands.add_parser('accept', help='accept supplied offline workflow execution evidence')
    command.add_argument('--format', required=True, choices=['n8n', 'make'])
    command.add_argument('--contract', required=True)
    command.add_argument('--execution', required=True)
    command.add_argument('--out', required=True, help='new JSON/Markdown output prefix')
    args = parser.parse_args()
    if args.command == 'init':
        try:
            workflow, _ = read(args.workflow)
            data = json.dumps(skeleton(workflow), indent=2, ensure_ascii=False) + '\n'
            with Path(args.out).open('x', encoding='utf-8') as handle:
                handle.write(data)
        except (OSError, ValueError, TypeError, RecursionError, MemoryError) as error:
            print(json.dumps({'status': 'UNKNOWN', 'error': 'INPUT_RESOURCE_LIMIT' if isinstance(error, MemoryError) else str(error)}), file=sys.stderr)
            return 3
        print(json.dumps({'operation': 'draft_created', 'status': 'UNKNOWN', 'output': args.out,
                          'next_action': 'Fill expected outputs independently, then run accept.'}))
        return 0
    report = accept(args.contract, args.execution, args.format)
    try:
        with Path(args.out + '.json').open('x', encoding='utf-8') as out:
            with Path(args.out + '.md').open('x', encoding='utf-8') as md:
                out.write(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
                md.write(markdown(report))
    except OSError as error:
        print(json.dumps({'status': 'UNKNOWN', 'error': str(error),
                          'next_action': 'Retain partial files, reconcile outputs and use a fresh prefix.'}), file=sys.stderr)
        return 3
    print(json.dumps(report, ensure_ascii=False))
    return {'PASS': 0, 'FAIL': 1, 'UNKNOWN': 2}[report['status']]


if __name__ == '__main__':
    sys.exit(main())
