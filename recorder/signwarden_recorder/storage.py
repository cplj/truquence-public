"""Private POSIX files and a serialized, append-only hash chain.

Modified 2026-10-20: public capture-only cut, no rule matching; do not propagate legacy risk labels.
"""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat

from .core import canonical, digest, parse

GENESIS = '0' * 64
MAX_LEDGER = 128 * 1024 * 1024


def root():
    return Path.home() / '.local' / 'state' / 'signwarden-recorder'


def private_dir(path):
    # Reject existing symlink components; never change another directory's mode.
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('symlink directory is not supported')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise ValueError('recorder directory must be owned by you with mode 0700')


@contextmanager
def locked(path, write=False):
    flags = os.O_RDWR | os.O_CREAT if write else os.O_RDONLY
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError('expected an owned regular file')
        fcntl.flock(fd, fcntl.LOCK_EX if write else fcntl.LOCK_SH)
        with os.fdopen(os.dup(fd), 'r+b' if write else 'rb') as stream:
            yield stream
    finally:
        os.close(fd)


def read_private(path):
    with locked(path) as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('file exceeds 1 MiB')
    return raw


def atomic(path, raw, mode=0o600):
    import tempfile
    if path.is_symlink():
        raise ValueError('refusing symlink target')
    fd, name = tempfile.mkstemp(prefix='.swr-', dir=path.parent)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(name, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def reversed_records(stream):
    stream.seek(0, 2)
    position = stream.tell()
    if position:
        stream.seek(position - 1)
        if stream.read(1) != b'\n':
            raise ValueError('incomplete ledger tail; preserve it for review')
    tail = b''
    while position:
        size = min(position, 65536)
        position -= size
        stream.seek(position)
        tail = stream.read(size) + tail
        lines = tail.split(b'\n')
        tail = lines[0]
        for line in reversed(lines[1:]):
            if line:
                yield parse(line)
        if len(tail) > 1024 * 1024:
            raise ValueError('ledger record too large')
    if tail:
        yield parse(tail)


def append(record):
    directory = root()
    private_dir(directory)
    with locked(directory / 'actions.jsonl', write=True) as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.seek(0, 2)
        if stream.tell() >= MAX_LEDGER:
            raise ValueError('ledger exceeds 128 MiB; archive it before continuing')
        previous = next(reversed_records(stream), None)
        if previous and previous.get('hash') != digest({k: v for k, v in previous.items() if k != 'hash'}):
            raise ValueError('ledger tail hash mismatch')
        record['seq'] = previous['seq'] + 1 if previous else 0
        record['prev_hash'] = previous['hash'] if previous else GENESIS
        if record['event'] in ('PostToolUse', 'PostToolUseFailure') and record['call_id']:
            for old in reversed_records(stream):
                if old.get('call_id') == record['call_id']:
                    if old['event'] == 'PreToolUse':
                        delta = record['time_ns'] - old['time_ns']
                        record['elapsed_ms'] = delta / 1e6 if delta >= 0 else None
                    break
        record['hash'] = digest(record)
        stream.seek(0, 2)
        stream.write(canonical(record) + b'\n')
        stream.flush()  # Acknowledgement means the complete record reached the kernel cache.
    return record


def read_records():
    path = root() / 'actions.jsonl'
    if not path.exists():
        return []
    result, previous = [], GENESIS
    with locked(path) as stream:
        if os.fstat(stream.fileno()).st_size > MAX_LEDGER + 1024 * 1024:
            raise ValueError('ledger exceeds read limit')
        for seq, line in enumerate(stream):
            if not line.endswith(b'\n'):
                raise ValueError('incomplete ledger tail')
            row = parse(line)
            if (not isinstance(row, dict) or row.get('seq') != seq or row.get('prev_hash') != previous
                    or row.get('hash') != digest({k: v for k, v in row.items() if k != 'hash'})):
                raise ValueError('ledger chain mismatch')
            previous = row['hash']
            result.append(row)
    return result


def sync_records():
    """Flush the ledger without holding its append lock, then persist its directory entry."""
    path = root() / 'actions.jsonl'
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError('expected an owned regular file')
        os.fsync(fd)
    finally:
        os.close(fd)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
