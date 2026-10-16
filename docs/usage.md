# Local usage

For v0.2 workflow execution evidence, see [workflow formats](workflows.md) and
the [real local n8n walkthrough](local-n8n.md). The sections below describe the
retained three-checker and CSV interfaces.

## Action Contract

The main command is `truquence accept`; see [contract reference](contracts.md).
The installed Python interface is `actioncontract.load`, `validate`, `hash`,
and `actioncontract.acceptance.accept`. Fixture discovery is shown in README.
Hash pins compare exact supplied bytes, including whitespace; a digest does
not authenticate the source. Use independent trusted reference digests.
If an export fails, preserve partial files and choose a fresh output prefix.

## Supplied-record reconciliation

```sh
truquence usage.csv billed.csv --confirm-atomic-events --out result.json
```

Use `python -m truquence.cli --help` for reconciliation arguments. CSV export
exit 0 means the file was created, including Failed or Unknown results.
Only inspect Ready under its stated caller-declared atomic-event scope.
An oversized file may report different observed-byte counts in CLI and HTTP:
the CLI reads a bounded prefix; HTTP already has the complete supplied body.
Neither path accepts oversized input.

# Local interface reference

Install from this directory with `pip install .`. The installed CLI and server
use the same `truquence.core.reconcile` function and policy `usage-events-1.0.0`.
`truquence --version` prints `0.1.0`. Packaged synthetic samples and web
assets also work after installation, outside the source directory.

## CSV input

Both files require this exact ordered header and at least one data row:

```csv
event_id,customer_id,period,unit,quantity
SYN-001,SYN-CUSTOMER,2026-10,request,2
```

The stable key is `(customer_id, period, event_id)`. IDs are nonempty, at most
128 characters, and cannot contain NUL. Reserved event IDs `TOTAL`, `AGGREGATE`
and `SUMMARY` are unsupported. Files must describe the same agreed scope, with
one pre-agreed atomic event per row; confirmation is the caller's declaration.
Each UTF-8 file (optional BOM) may be at most 524288 bytes and 10000 data rows;
each CSV field may be at most 4096 characters. Periods are `YYYY-MM`, years
0001–9999 and months 01–12. Units: `request`, `token`, `second`. Quantities are
unsigned decimals from 0 through 1000000000000 with up to six decimal places;
no leading zeros except zero itself, exponent notation, signs or whitespace.

## HTTP request

Start `python -m truquence.server`; it binds only `127.0.0.1:8769`.
`POST /check` requires `Content-Type: application/json`, a single Content-Length,
and exactly these keys (base64 values contain the complete CSV bytes):

```json
{"usage_csv_base64": "...", "billed_csv_base64": "...", "confirm_atomic_events": true}
```

The two CSV values are strings; confirmation is a JSON boolean. Duplicate or
extra keys and invalid base64 are rejected. Request bodies are limited to
1402197 bytes; transfer encoding is unsupported. Host must be
`127.0.0.1:8769`. Origin may be absent for API clients; when supplied it must be
exactly `http://127.0.0.1:8769`. There is no cross-origin permission. Uploaded
bytes are processed in memory and are not saved. `GET /` serves the included
interface; `/sample/clean`, `/sample/dirty`, `/sample/unknown` return synthetic
payloads with extra display-name fields (remove those before POST).

HTTP 200 returns a completed comparison, including `Failed` and `Unknown`:

```json
{"policy_version":"usage-events-1.0.0","state":"Ready","scope":"Provided records only; caller-declared atomic event scope. No source completeness, money/tax, API or customer acceptance verified.","atomic_scope_caller_declared":true,"inputs":{"usage":{"sha256":"...","bytes":94,"hash_scope":"exact_provided_bytes","observed_bytes":94},"billed":{"sha256":"...","bytes":94,"hash_scope":"exact_provided_bytes","observed_bytes":94}},"counts":{"usage_rows":1,"billed_rows":1,"valid_usage_rows":1,"valid_billed_rows":1,"matched_events":1,"error_findings":0,"unknown_findings":0},"findings":[]}
```

This is an illustrative shape; byte counts/hashes come from the exact input.
`Ready` means the supplied rows match under the caller-declared contract.
`Failed` means definite duplicate/missing/quantity errors. `Unknown` means
unsupported or insufficient input/conditions (including different units).
Invalid CSV yields HTTP 200 `Unknown` with findings; it is never accepted as a
match. Findings include a code, severity and next action. Fix the inputs and
rerun; this tool does not decide which record is authoritative.

Request/protocol errors use HTTP 400/403/404/411/413/415 and JSON such as
`{"error":"INVALID_REQUEST","state":"Unknown"}`. They contain no completed
comparison. A failed connection or timeout likewise provides no usable result;
do not infer `Ready`. The CLI exports a full report exclusively to a new file;
it never overwrites one. If writing fails, retain any partial file and inspect
it before retrying. CLI exit 0 reports export success, not acceptance.

## Test and CI

After installation run `python -m unittest discover -s tests/product -v` from this
directory. Tests cover the core, installed CLI, local HTTP JSON interface,
packaged assets and error/unknown/boundary cases without external services.

## Container CLI

```sh
docker build -t truquence .
docker run --rm -v "$PWD:/work" truquence accept --contract /work/contract.json --results /work/authorization.json /work/recovery.json /work/completion.json --out /work/acceptance
```

Building needs the base image and build tool. The image defaults to the CLI;
the loopback HTTP service is not exposed. Input files are caller-supplied.

## Tests

After installation, from the repository root:

```sh
python3 -m unittest discover -s tests/product -v
python3 -m unittest discover -s tests/actioncontract -v
```

The examples contain no real accounts. Three checker fixtures are hand-authored
and are not evidence of running those services or a payment provider.

HTTP resource limits: at most 8 concurrent connections, a 5-second total header deadline and a separate 5-second total body deadline. Excess connections return 503 SERVER_BUSY; body timeouts return 408 REQUEST_TIMEOUT. The web client permits only the exact loopback origin and four fixed API paths, with redirects disabled; arbitrary remote, private-network, link-local and metadata targets are rejected. There is no outbound Python HTTP client.
