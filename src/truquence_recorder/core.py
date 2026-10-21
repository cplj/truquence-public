"""Bounded input and secret masking.

Modified 2026-10-20: public capture-only cut, no rule matching; retain capture validation and masking only.
"""
import base64
import hashlib
import json
import re

MAX_INPUT = 1024 * 1024
EVENTS = ('SessionStart', 'PreToolUse', 'PostToolUse', 'PostToolUseFailure', 'SessionEnd')
SECRET_KEY = re.compile(r'[\w.-]*(?:password|passwd|secret|token|authorization|api.?key|credentials?|private.?key|secret.?access.?key)', re.I)
SECRET_FLAG = re.compile(r'--(?:password|token|api-key|secret)', re.I)
PATTERNS = [
    re.compile(r'-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)'),
    re.compile(r'\b(?:sk-[A-Za-z0-9_-]{8,}|sk_live_[A-Za-z0-9_-]{8,}|hf_[A-Za-z0-9_]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,}|xox[baprs]-[A-Za-z0-9-]{8,}|AKIA[A-Z0-9]{16}|ASIA[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{20,})\b'),
    re.compile(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b'),
    re.compile(r'(?i)\bBearer\s+[A-Za-z0-9_./+=-]+'),
    re.compile(r'(?<![\w.-])' + SECRET_KEY.pattern + r'["\x27]?\s*[=:]\s*(?:"[^"\n]*"|\x27[^\x27\n]*\x27|[^\s&;,]+)', re.I),
    re.compile(r'(?i)\b(?:aws_secret_access_key|_authToken)\s+(?:"[^"\n]*"|\x27[^\x27\n]*\x27|[^\s&;,]+)'),
    re.compile(r'(?i)(?:https?|postgres(?:ql)?|mysql|redis)://[^\s/@:]+:[^\s/@]+@'),
    re.compile(r'(?i)(?:--(?:password|token|api-key|secret)\s+)(?:"[^"\n]*"|\x27[^\x27\n]*\x27|\S+)'),
    re.compile(r'(?i)\bcurl\b[^\n;&|]*?\s(?:-u|--user)(?:\s+|=)(?:"[^"\n]*:[^"\n]*"|\x27[^\x27\n]*:[^\x27\n]*\x27|[^\s&;,]+:[^\s&;,]+)'),
]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def parse(raw):
    if len(raw) > MAX_INPUT:
        raise ValueError('input exceeds 1 MiB')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('non-finite JSON number')
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
        # Bound nesting explicitly; interpreter recursion limits vary by version.
        pending = [(value, 0)]
        while pending:
            item, depth = pending.pop()
            if depth > 64:
                raise ValueError('JSON nesting exceeds 64 levels')
            if isinstance(item, dict):
                pending.extend((child, depth + 1) for child in item.values())
            elif isinstance(item, list):
                pending.extend((child, depth + 1) for child in item)
        canonical(value)
        return value
    except (UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError('invalid JSON encoding or depth') from exc


def mask_basic(match):
    try:
        if b':' in base64.b64decode(match[1], validate=True):
            return '[REDACTED]'
    except ValueError:
        pass
    return match[0]


def text_mask(value):
    value = re.sub(r'(?i)\bBasic\s+([A-Za-z0-9+/]+={0,2})(?![A-Za-z0-9_./+=-])', mask_basic, value)
    for pattern in PATTERNS:
        value = pattern.sub('[REDACTED]', value)
    # Terminal control sequences and bidi controls remain visible data, not commands.
    return ''.join(c if c.isprintable() else '\\u%04x' % ord(c) for c in value)


def redact(value, depth=0):
    if depth > 32:
        return '[OMITTED: depth]'
    if isinstance(value, dict):
        return {text_mask(k): '[REDACTED]' if SECRET_KEY.fullmatch(k) else redact(v, depth + 1)
                for k, v in value.items()}
    if isinstance(value, list):
        return ['[REDACTED]' if i and isinstance(value[i - 1], str) and SECRET_FLAG.fullmatch(value[i - 1])
                else redact(v, depth + 1) for i, v in enumerate(value)]
    return text_mask(value) if isinstance(value, str) else value


def summarize(arguments):
    # File contents and tool output are not needed to identify the action.
    output = {}
    for key, value in arguments.items():
        if key in ('content', 'old_string', 'new_string', 'edits'):
            output[key] = '[OMITTED: file content]'
        elif SECRET_KEY.fullmatch(key):
            output[text_mask(key)] = '[REDACTED]'
        else:
            clean = redact(value)
            output[text_mask(key)] = clean if not isinstance(clean, (dict, list)) else canonical(clean).decode()
            if isinstance(output[text_mask(key)], str):
                output[text_mask(key)] = output[text_mask(key)][:2048]
    # Bound the final record even for many argument keys.
    if len(canonical(output)) > 16384:
        return {'summary': '[OMITTED: arguments exceed summary limit]'}
    return output


def hook_input(raw):
    value = parse(raw)
    if not isinstance(value, dict) or value.get('hook_event_name') not in EVENTS:
        raise ValueError('unsupported hook event')
    for key in ('session_id', 'cwd'):
        if not isinstance(value.get(key), str) or not value[key] or len(value[key]) > 4096:
            raise ValueError('missing or invalid hook metadata')
    if value['hook_event_name'] in EVENTS[1:4]:
        if not isinstance(value.get('tool_name'), str) or not value['tool_name'] or len(value['tool_name']) > 256:
            raise ValueError('missing tool name')
        if not isinstance(value.get('tool_input'), dict):
            raise ValueError('tool_input must be an object')
        if 'tool_use_id' in value and (not isinstance(value['tool_use_id'], str) or len(value['tool_use_id']) > 4096):
            raise ValueError('invalid tool_use_id')
    return value
