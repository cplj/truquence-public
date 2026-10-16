# Truquence

Check whether supplied authorization, recovery and completion evidence agrees with a synthetic action contract before accepting an action.

## Quick start

Requires Git, Python 3.10+ with venv/pip and a POSIX shell. Setup may fetch setuptools; samples run offline without an account.

```sh
git clone https://github.com/cplj/truquence-public.git
cd truquence-public
python3 -m venv .venv && . .venv/bin/activate && python3 -m pip install .
TQ_EXAMPLES="$(python3 -c 'import actioncontract; from pathlib import Path; print(Path(actioncontract.__file__).parent)')"
TQ_OUT="$(mktemp -d)"
truquence accept --contract "$TQ_EXAMPLES/contracts/synthetic.json" --results "$TQ_EXAMPLES/samples/sw.json" "$TQ_EXAMPLES/samples/ax.json" "$TQ_EXAMPLES/samples/ks.json" --out "$TQ_OUT/acceptance"
```

Actual sample output (JSON excerpt):
```json
{"status":"PASS","counts":{"PASS":3,"FAIL":0,"UNKNOWN":0}}
```
Writes stdout JSON, `$TQ_OUT/acceptance.json` and `.md`. Hand-authored synthetic results do not prove external execution.

## For AI agents

Run the commands above; replace all four input paths for your own evidence. `--results` order and JSON check keys: authorization=`signwarden`, recovery=`axiocairn`, completion=`kinesift`.
Exit 0 PASS, 1 FAIL, 2 UNKNOWN, 3 output/signing error; argparse usage errors also exit 2. FAIL and UNKNOWN block acceptance. Inspect `status`, `findings` and each action's `checks`; never infer retry permission.

## Common errors

- `externally-managed-environment` or command missing: activate `.venv` and repeat installation there.
- Missing venv/pip or old Python: provide Python 3.10+ with venv/pip.
- Missing/invalid input: correct paths in `inputs`/`findings`, then rerun.
- Output exists: retain partial files, reconcile them, then choose a fresh prefix.

[Inputs and outputs](docs/contracts.md) · [Agent reference](llms.txt) · [CSV/API](docs/usage.md)

[Workflow acceptance](docs/workflows.md)
