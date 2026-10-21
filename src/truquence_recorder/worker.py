"""Single local worker. Replies acknowledge a kernel-cache append; fsync runs in batches."""
import fcntl
import os
from pathlib import Path
import signal
import socket
import stat
import struct
from threading import Event, Thread

from .core import MAX_INPUT, canonical, hook_input
from .hook import handle
from .storage import private_dir, sync_records


def receive(connection, length):
    data = bytearray()
    while len(data) < length:
        block = connection.recv(length - len(data))
        if not block:
            raise ValueError('incomplete request')
        data.extend(block)
    return bytes(data)


def expired(_signum, _frame):
    raise TimeoutError('recording deadline')


def shutdown(_signum, _frame):
    raise SystemExit(0)


def batch_sync(stop, pending):
    # Leave half the 200ms budget for scheduling and the sync itself.
    while not stop.wait(0.1):
        if pending.is_set():
            pending.clear()
            try:
                sync_records()
            except (OSError, ValueError):
                pending.set()  # Retry storage failures without delaying client replies.


def serve(directory):
    directory = Path(directory)
    private_dir(directory)
    # Lifecycle lock prevents a slow or concurrent startup from replacing a live socket.
    fd = os.open(directory / 'worker.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(fd, 'r+b') as lock:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('expected a private owned worker lock')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        path = directory / 'socket'
        if path.is_symlink():
            raise ValueError('refusing symlink socket')
        if path.exists():
            info = path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError('expected an owned socket')
            path.unlink()
        signal.signal(signal.SIGALRM, expired)
        signal.signal(signal.SIGTERM, shutdown)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            os.umask(0o077)
            listener.bind(str(path))
            listener.listen(128)
            listener.settimeout(300)
            stop, pending = Event(), Event()
            syncer = Thread(target=batch_sync, args=(stop, pending), daemon=True)
            syncer.start()
            try:
                while True:
                    try:
                        connection, _ = listener.accept()
                    except TimeoutError:
                        return
                    with connection:
                        connection.settimeout(0.75)
                        signal.setitimer(signal.ITIMER_REAL, 0.75)
                        try:
                            home_size, runner_size, size = struct.unpack('=III', receive(connection, 12))
                            if home_size > 8192 or runner_size > 8192 or size > MAX_INPUT:
                                raise ValueError('request exceeds limit')
                            home = os.fsdecode(receive(connection, home_size))
                            runner = os.fsdecode(receive(connection, runner_size))
                            if home != os.environ.get('HOME') or runner != str(Path(__file__).with_name('runner.py').resolve()):
                                raise ValueError('worker identity mismatch')
                            result = canonical(handle(hook_input(receive(connection, size)))) + b'\n'
                            pending.set()
                            connection.sendall(b'\0' + struct.pack('=I', len(result)) + result)
                        except (ValueError, OSError, TypeError, KeyError, RecursionError):
                            try:
                                connection.sendall(b'\1' + struct.pack('=I', 0))
                            except OSError:
                                pass
                        finally:
                            signal.setitimer(signal.ITIMER_REAL, 0)
            finally:
                stop.set()
                syncer.join()
                try:
                    sync_records()
                finally:
                    path.unlink(missing_ok=True)
