# A real local n8n execution, from an empty Python environment

Python 3.10+, Node 20.19–24.x and npm must already be available. n8n 2.0.0
is pinned for this recipe. Its first download may take several minutes and
requires registry access; subsequent execution is local. No cloud account,
login, license activation or remote workflow service is used. Run from the
source checkout's root (the directory containing pyproject.toml).

Copy the following into a POSIX shell. It creates a **new workflow** with a fresh
reference, defines expected outputs before execution, imports it into an
isolated local n8n database, runs it, exports its actual execution and checks it.
No packaged fixture is read. The workflow uses only Manual Trigger and Edit
Fields, with no credentials, network nodes or customer data.

```sh
TQ_NODE_DIR="$(dirname "$(command -v node)")"
TQ_RUN="$(mktemp -d)"
export TQ_RUN
python3 -m venv "$TQ_RUN/venv"
. "$TQ_RUN/venv/bin/activate"
export PATH="$VIRTUAL_ENV/bin:$TQ_NODE_DIR:$PATH"
node --version
python3 -m pip install .
python3 - <<'PY'
import json, os, uuid
from pathlib import Path
p = Path(os.environ['TQ_RUN'])
reference = str(uuid.uuid4())
workflow = {
    'id': 'TruquenceLocal02', 'versionId': str(uuid.uuid4()), 'active': False, 'name': 'Local acceptance ' + reference,
    'nodes': [
        {'id': 'start', 'name': 'Start', 'type': 'n8n-nodes-base.manualTrigger',
         'typeVersion': 1, 'parameters': {'notice': ''}, 'position': [0, 0]},
        {'id': 'result', 'name': 'Result', 'type': 'n8n-nodes-base.set',
         'typeVersion': 3.4, 'position': [240, 0], 'parameters': {
             'mode': 'manual', 'duplicateItem': False, 'includeOtherFields': False,
             'assignments': {'assignments': [
                 {'id': 'ref', 'name': 'reference', 'type': 'string', 'value': reference},
                 {'id': 'qty', 'name': 'quantity', 'type': 'number', 'value': 7}]},
             'options': {}}}],
    'connections': {'Start': {'main': [[{'node': 'Result', 'type': 'main', 'index': 0}]]}},
    'settings': {'executionOrder': 'v1'}}
(p / 'workflow.json').write_text(json.dumps(workflow))
(p / 'expected.json').write_text(json.dumps({'Start': [{}], 'Result': [{'reference': reference, 'quantity': 7}]}))
PY
truquence init --workflow "$TQ_RUN/workflow.json" --out "$TQ_RUN/contract.json"
python3 - <<'PY'
import json, os
from pathlib import Path
p = Path(os.environ['TQ_RUN'])
contract = json.loads((p / 'contract.json').read_text())
expected = json.loads((p / 'expected.json').read_text())
for check in contract['x-checks']:
    check['x-expect_items'] = expected[check['x-node']]
(p / 'contract.json').write_text(json.dumps(contract, indent=2))
PY
export N8N_USER_FOLDER="$TQ_RUN/n8n-local"
export N8N_DIAGNOSTICS_ENABLED=false N8N_VERSION_NOTIFICATIONS_ENABLED=false
export N8N_TEMPLATES_ENABLED=false N8N_RUNNERS_ENABLED=false
export N8N_LOG_LEVEL=info
npx --yes --package=n8n@2.0.0 n8n import:workflow --input="$TQ_RUN/workflow.json" > "$TQ_RUN/import.log" 2>&1
npx --yes --package=n8n@2.0.0 n8n execute --id=TruquenceLocal02 --rawOutput > "$TQ_RUN/execute.stdout" 2> "$TQ_RUN/execute.stderr"
python3 - <<'PY'
import json, os, sqlite3
from pathlib import Path
p = Path(os.environ['TQ_RUN'])
db = p / 'n8n-local/.n8n/database.sqlite'
# Read ONLY the execution tables of the isolated database just created above.
with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as con:
    rows = con.execute("SELECT e.id,e.finished,e.status,e.startedAt,e.stoppedAt,d.workflowData,d.data FROM execution_entity e JOIN execution_data d ON d.executionId=e.id WHERE e.workflowId=?", ('TruquenceLocal02',)).fetchall()
if len(rows) != 1:
    raise SystemExit('Expected exactly one execution; retain logs and review.')
run_id, finished, status, started, stopped, snapshot, data = rows[0]
# n8n stores execution data as a flatted string-reference table. Decode the
# acyclic execution tree, preserving strings/numbers exactly; cycles stop export.
table = json.loads(data)
def expand(index, active=()):
    if index in active:
        raise ValueError('Cyclic execution data requires a full n8n JSON export')
    item = table[index]
    def value(v):
        return expand(int(v), active + (index,)) if isinstance(v, str) else v
    if isinstance(item, dict):
        return {k: value(v) for k, v in item.items()}
    if isinstance(item, list):
        return [value(v) for v in item]
    return item
execution = {'id': str(run_id), 'finished': bool(finished), 'status': status,
             'startedAt': started, 'stoppedAt': stopped,
             'workflowData': json.loads(snapshot), 'data': expand(0)}
(p / 'execution.json').write_text(json.dumps(execution, indent=2))
PY
truquence accept --format n8n --contract "$TQ_RUN/contract.json" --execution "$TQ_RUN/execution.json" --out "$TQ_RUN/report"
cat "$TQ_RUN/report.md"
printf 'Retained files: %s\n' "$TQ_RUN"
```

Expected: `PASS`, scope `execution_observation`, business acceptance `UNKNOWN`;
four passing checks (execution, workflow identity, Start, Result). The report compares every output
object, count and order. Change expected quantity to 8: `FAIL` / exit 1. Leave
an expectation `null`: `UNKNOWN` / exit 2. No action is retried by Truquence.
Keep the artifacts for review; the command exits and leaves no n8n server running.

For your own workflows, supply your exported JSON to `init` and independently
fill each node's expected items. The adapter requires the execution's full
`workflowData` snapshot and `data.resultData.runData`. It covers JSON-only,
single-output-branch nodes; multi-branch/binary or incomplete exports are UNKNOWN.
Use only files you are authorized to inspect. Imported workflows can execute
arbitrary actions: run only workflows you have reviewed and authorized.

The CLI raw output is retained for diagnosis. In n8n 2.0.0 it can say `running`
even after completion and omit `workflowData`; passing that incomplete object
directly to accept stays UNKNOWN. The recipe instead exports the completed
execution row, full workflow snapshot and stored execution data from its own
isolated SQLite database in read-only mode. It never invents a terminal status.
No existing n8n instance or credentials table is read.

Workflow fingerprints include runtime parameters. If n8n adds node defaults to
your export, review its execution workflowData snapshot and generate a new
contract from that complete configuration before a fresh run. Do not simply
replace the fingerprint to approve the execution under review. This recipe
explicitly sets the defaults for its two pinned node versions.
