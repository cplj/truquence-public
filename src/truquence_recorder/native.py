"""Prepare the local native transport; recording still uses the Python validators."""
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

from .storage import locked, private_dir, root


def ensure_client():
    private_dir(root())
    directory = root() / 'native'
    private_dir(directory)
    source = Path(__file__).with_name('client.c')
    # A source digest avoids reusing a client from a different installed version.
    import hashlib
    target = directory / ('client-' + hashlib.sha256(source.read_bytes()).hexdigest()[:16])
    with locked(directory / 'build.lock', write=True):
        if target.is_symlink():
            raise ValueError('refusing symlink client')
        if not target.exists():
            fd, name = tempfile.mkstemp(prefix='.client-', dir=directory)
            os.close(fd)
            try:
                try:
                    subprocess.run(['/usr/bin/cc', '-O2', '-std=c99', '-Wall', '-Wextra', str(source), '-o', name],
                                   check=True, capture_output=True, timeout=30)
                except subprocess.SubprocessError:
                    raise ValueError('native client compilation failed') from None
                os.chmod(name, 0o700)
                os.replace(name, target)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
        info = target.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o777 != 0o700 or not target.is_file():
            raise ValueError('expected a private owned native client')
    return target


def hook_command():
    return 'exec ' + shlex.join([str(ensure_client()), sys.executable, str(Path(__file__).with_name('runner.py').resolve())])

