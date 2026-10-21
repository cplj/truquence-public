# Workflow contract and evidence reference

`truquence accept --format n8n|make --contract FILE --execution FILE --out PREFIX`
writes PREFIX.json and PREFIX.md exclusively; prior files are never overwritten.
A collision may reserve an empty JSON file before failing: retain it and use a
new prefix after reconciliation. JSON is strict UTF-8: duplicate keys, nonfinite
numbers, malformed data and files over 1 MiB produce UNKNOWN. Argument errors
exit 2; output errors exit 3. No input causes a network call or workflow execution.

## n8n

`truquence init --workflow workflow.json --out contract.json` reads one exported
workflow object (not an array) and creates this independent v0.2 contract shape:

```json
{
  "x-schema": "truquence.workflow-contract.v0.2",
  "x-source": "n8n",
  "x-scope": "execution_observation",
  "x-workflow_sha256": "<generated execution-configuration fingerprint>",
  "x-checks": [
    {"x-node": "Result", "x-expect_runs": 1, "x-expect_items": null}
  ]
}
```

Each enabled node needs one check; `init` includes them all. Replace null with
an independently defined array of JSON objects; an empty array explicitly expects
zero items. Run counts, item counts, values and order must match exactly. Runtime
workflow identity and configuration (ID, nodes, connections, settings) must match the fingerprint;
editor positions, notes and colors are ignored. Changed runtime configuration
requires a newly reviewed contract. Do not generate expected output from the
execution being accepted.

### Example: the run says success, the output is wrong

An n8n run can finish green while a node passes the wrong data along. With the
package installed ([Quick start](quickstart.md)), check one full exported execution offline:

```sh
truquence init --workflow workflow.json --out contract.json
# edit contract.json: replace each "x-expect_items": null with the items that node should output
truquence accept --format n8n --contract contract.json --execution execution.json --out run
```

Actual synthetic run: the execution reports `"status": "success"`, but node
`Total` outputs `"total": 12.0` where the contract expects `120.0`. Exit 1, JSON excerpt:

```json
{"status":"FAIL","counts":{"PASS":2,"FAIL":1,"UNKNOWN":0}}
{"id":"Total","status":"FAIL","reason":"Exact JSON output items differ from expected (including item count and order)."}
```

The same contract against an execution with the right total returns PASS (exit 0).
A `null` expectation stays UNKNOWN.
For Make, only the log's ID, reported status and operation count are checked, not outputs (see below).

Supported execution: one full JSON object containing `finished`, optional
`status`, `workflowData`, and `data.resultData.runData`. Each checked node maps
to an array of runs, each containing `data.main: [[{"json": {}}]]`. `finished`
must be true with status success or omitted (older CLI exports). Error/crashed/
canceled states and node errors FAIL, including errors on unchecked nodes.
Unfinished/waiting/unknown statuses, missing workflow snapshots or node output,
coverage gaps, multiple output branches and binary items are UNKNOWN. This
release intentionally requires every enabled node; conditional workflows with
unexecuted branches need review and cannot silently pass. Full execution exports
are supported. An incomplete CLI `execute --rawOutput` object stays UNKNOWN; workflow-only exports,
console transcripts, compact/flatted database internals and lists are UNKNOWN.

[Local execution walkthrough](local-n8n.md). Sources:
[n8n Server CLI](https://docs.n8n.io/hosting/cli-commands/),
[n8n execute source](https://github.com/n8n-io/n8n/blob/master/packages/cli/src/commands/execute.ts).
Validated locally against pinned n8n 2.0.0, without hosted services.

## Make scenario log adapter

Use an **already exported** scenario-log JSON response. Truquence never calls
Make or asks for credentials. Supported envelopes: `{"scenarioLog": {...}}`,
`{"scenarioLogs": [...]}`, or one log row. Select exactly one row by execution
ID; duplicate/missing matches are UNKNOWN. Additional unrelated rows are ignored
only because the contract explicitly pins the desired execution ID.

Create a contract manually (IDs below are placeholders for your export):

```json
{
  "x-schema": "truquence.workflow-contract.v0.2",
  "x-source": "make",
  "x-scope": "execution_observation",
  "x-scenario_id": 1229,
  "x-execution_id": "your-exported-execution-id",
  "x-expect_operations": 10
}
```

The row needs `id`, `imtId` containing `_scenario.1229.` (or explicit `scenarioId`),
`type` (`auto`, `manual` or `instant`), integer `status` and `operations`. Status
1 is success; 2 warning is UNKNOWN; 3 error is FAIL. A paused execution is UNKNOWN
even if a stale status says success. Missing/unknown status or log type is UNKNOWN.
Incorrect scenario/operation count FAIL. Boolean status/counts are invalid.
A successful count comparison verifies only the provided log's identity, reported
success and operation count. It does not verify outputs, module side effects or
scenario completeness. CSV history, module logs and execution-detail responses
with different shapes are unsupported and UNKNOWN. Make cannot run locally;
this adapter is validated against the official public schema and synthetic
format cases, with **no live Make execution claim**.

[Make official log schema and status codes](https://developers.make.com/api-documentation/api-reference/scenarios/logs).

## Report output and scope

JSON fields: `policy_version`, `status` (PASS/FAIL/UNKNOWN), `state`
(Ready/Failed/Unknown), `source`, `scope`, `limitations`, `business_acceptance`
(always UNKNOWN), `inputs` (exact-byte SHA-256 and byte counts), `counts` and
`checks` (id, status, reason). Markdown includes the same decision and reasons.
FAIL takes precedence over UNKNOWN when a definite failure is observed. Input
errors are UNKNOWN; output failures do not return success. Hashes provide
integrity references, not origin authentication or signatures. Customer acceptance,
authorization, receipts/recovery and durable external effects need independent
evidence; this adapter does not fabricate the three checkers' results.
The synthetic Action Contract v0 schema and three-checker merger remain separate
and retain their existing behavior (`truquence accept --contract ... --results ...`).
