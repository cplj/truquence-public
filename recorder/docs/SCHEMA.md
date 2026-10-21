<!-- Public capture-only cut, 2026-10-20; no rule matching. -->

# Recorder format

Each line in `actions.jsonl` is one canonical JSON object followed by a newline. The compatible schema identifier is `signwarden.recorder.v1`. Canonical JSON sorts object keys, uses compact separators and ASCII escaping, and rejects non-finite numbers.

| Field | Meaning |
| --- | --- |
| `schema` | `signwarden.recorder.v1` |
| `evidence_level` | `self_reported` for new hook records; legacy rows may omit it |
| `time_ns` | Recorder wall-clock time in nanoseconds; not a trusted timestamp |
| `session`, `cwd` | Redacted hook metadata |
| `event`, `tool` | Supported hook event and optional tool name |
| `arguments` | Redacted, bounded argument summary; file-content fields omitted |
| `result_code` | Integer tool response exit code when supplied, otherwise null |
| `status` | `requested`, `succeeded`, `failed` or `observed`, derived from hook metadata |
| `elapsed_ms` | Wall-clock delta from a matching captured pre-event, otherwise null |
| `risks` | Empty array for new records; existing rows are preserved |
| `call_id` | SHA-256 of canonical `[session_id, tool_use_id]`, or null |
| `seq` | Zero-based line sequence |
| `prev_hash` | Prior record hash; 64 zeroes for the first record |
| `hash` | SHA-256 of canonical record with the `hash` field omitted |

`verify` checks each line's complete newline, sequence, previous hash and digest. An empty or absent ledger has a head of 64 zeroes. Successful verification reports `SELF_CONSISTENT` for the bytes read, with `completeness` and `authenticity` both `UNKNOWN`.

The ledger has a 128 MiB append limit and bounded reads. Existing incomplete tails and hash mismatches are preserved and rejected rather than repaired automatically. Record files are owned regular files opened without following symlinks; the state directory must be private to its owner.
