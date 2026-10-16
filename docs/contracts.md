# Action Contract inputs and report output

[Contract schema](../src/actioncontract/schema/action_contract.schema.json)
requires `x-schema: truquence.action-contract.v0`, a nonempty `x-version`,
`x-data_mode: SYNTHETIC` and nonempty `x-tasks`. Each action specifies its ID,
tool, account, version, actor, principal, tenant, scope, allowed actions,
forbidden state, expected effect count, payload and acceptance text. Its
expectation strategy declares approval, denial and recovery handling. Four MCP
boolean hints are declarations. Application payload keys are opaque data.

## Evidence inputs, in command order

1. Authorization: [sample](../src/actioncontract/samples/sw.json). An object with
   `cases`; each case matches an action `id` and includes `result`, `checks`,
   `not_executed_steps`, `stopped_reason` and `ledger`. Every expected/observed
   check, exact payload and expected total effect count must agree.
2. Recovery: [sample](../src/actioncontract/samples/ax.json). A list of records
   containing string `id`, `tool`, `payload`, `version`, `state`, `detail`.
   `tool` and `payload` contain JSON text. Identity, payload and version must
   match the contract; COMPLETED represents one matching effect. Unresolved
   recovery never grants retry permission.
3. Completion: [sample](../src/actioncontract/samples/ks.json). A list of
   `kinesift.run.v1` records with SYNTHETIC `data_mode`, matching `task`,
   `status`, boolean `accepted` and `verification` containing boolean
   `task_state_exact`, list `forbidden_mutations`, nonnegative integer
   `forbidden_attempts`, and boolean `accepted`. Declared success must agree
   with exact final-state and zero-forbidden-effect checks.

Missing, duplicate, unmapped or malformed evidence cannot pass. A recovery
COMPLETED count contradicting authorization/contract effect counts fails.
These formats are native supplied-result shapes; the program does not invoke
or connect to their originating checkers.

JSON keys retain native names: `signwarden` = authorization,
`axiocairn` = recovery, `kinesift` = completion, in that command order.

## Error handling

Missing or malformed inputs produce an UNKNOWN report (exit 2). Inspect
`inputs.<name>.path` and `findings` (`input`, `detail`, `next_action`), correct
the supplied file, and rerun with a fresh output prefix. Usage errors also exit
2, with argparse help on stderr and no report. Output errors exit 3 and emit
stderr JSON with `status`, `error`, `next_action`; retain and reconcile partial
files before selecting a fresh prefix. No error authorizes an external retry.
CSV export errors exit 2 with `operation: export_failed`, `state: Unknown`,
`error`, `path`, `detail`, `next_action` on stderr. CSV exit 0 confirms export;
inspect its report state separately.

## Output schema

The JSON report has `policy_version: action-contract-v0`, `status` in PASS/FAIL/UNKNOWN,
`state` in Ready/Failed/Unknown, `counts` with integer PASS/FAIL/UNKNOWN totals,
`inputs` containing supplied paths, exact-byte SHA256 and byte counts, `findings`,
and an `actions` list. Each action has `id`, `status` and per-checker `checks`
with status and reason. See the implementation for additional descriptive
fields. Markdown renders the same decision, actions, reasons and limits.

Any FAIL dominates UNKNOWN; UNKNOWN dominates PASS. Invalid contracts evaluate
no actions and return UNKNOWN. Input read errors have no valid completed
assessment. Acceptance exits 0/1/2 follow the report decision; exit 3 means an
output error and may leave partial files. Reports are unsigned and cannot
establish authenticity, actual external state, or business acceptance.

Input limits: each contract/checker is at most 1 MiB, each JSON container at most 1000 members, depth at most 64 and total nodes at most 20000. Oversized inputs return UNKNOWN with INPUT_LIMIT_EXCEEDED; allocation failure returns INPUT_RESOURCE_LIMIT. Rejected file bytes have no fingerprint.
