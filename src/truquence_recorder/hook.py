"""Hook process entrypoint; no SDK or CLI parser on this hot path.

Modified 2026-10-20: public capture-only cut, no rule matching; record events without permission decisions.
"""
import sys
import time
from .core import MAX_INPUT, canonical, digest, hook_input, redact, summarize
from .storage import append


def handle(value):
    event = value['hook_event_name']
    response = value.get('tool_response', {})
    code = response.get('exit_code') if isinstance(response, dict) else None
    if type(code) is not int:
        code = None
    status = ('failed' if event == 'PostToolUseFailure' or (code is not None and code != 0) or (isinstance(response, dict) and response.get('isError') is True)
              else 'succeeded' if event == 'PostToolUse' else 'requested' if event == 'PreToolUse' else 'observed')
    record = redact({'schema': 'signwarden.recorder.v1', 'time_ns': time.time_ns(),
                     'evidence_level': 'self_reported', 'session': value['session_id'], 'event': event, 'tool': value.get('tool_name'),
                     'cwd': value['cwd'], 'arguments': summarize(value.get('tool_input', {})),
                     'result_code': code, 'status': status, 'elapsed_ms': None, 'risks': [],
                     'call_id': digest([value['session_id'], value['tool_use_id']]) if value.get('tool_use_id') else None})
    append(record)
    return {}


def main():
    try:
        result = handle(hook_input(sys.stdin.buffer.read(MAX_INPUT + 1)))
    except (ValueError, OSError, TypeError, KeyError, RecursionError) as exc:
        # Never echo untrusted input or use exit 2 (a blocking hook verdict).
        print('Truquence Recorder could not record this event (' + type(exc).__name__ + ').', file=sys.stderr)
        return 1
    print(canonical(result).decode())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
