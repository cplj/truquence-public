"""Reversible user hook settings with a durable restore journal."""
import base64
import os
from pathlib import Path
import time

from .core import EVENTS, canonical, parse
from .storage import atomic, locked, private_dir, read_private, root


def hook_command():
    from .native import hook_command as native_hook_command
    return native_hook_command()


def settings_path():
    configured = os.environ.get('CLAUDE_CONFIG_DIR')
    path = Path(configured) if configured else Path.home() / '.claude'
    if not path.is_absolute():
        raise ValueError('CLAUDE_CONFIG_DIR must be absolute')
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('symlink settings directory is not supported')
    return path / 'settings.json'


def install():
    directory = root()
    private_dir(directory)
    with locked(directory / 'install.lock', write=True):
        settings = settings_path()
        journal = directory / 'installation.json'
        if journal.exists():
            prior = parse(read_private(journal))
            if str(settings) != prior['path']:
                raise ValueError('installation belongs to a different settings path')
            current = read_private(settings) if settings.exists() else None
            original = base64.b64decode(prior['original']) if prior['existed'] else None
            installed = base64.b64decode(prior['installed'])
            if current == installed:
                return 'already installed'
            if current == original:
                atomic(settings, installed, prior['mode'])
                return 'installed from retained journal'
            raise ValueError('settings changed; preserve changes before retrying')
        original = read_private(settings) if settings.exists() else b''
        if len(original) > 256 * 1024:
            raise ValueError('settings exceed the 256 KiB backup limit')
        config = parse(original) if settings.exists() else {}
        if not isinstance(config, dict) or not isinstance(config.get('hooks', {}), dict):
            raise ValueError('settings and hooks must be objects')
        existed = settings.exists()
        mode = settings.stat().st_mode & 0o777 if existed else 0o600
        hooks = config.setdefault('hooks', {})
        for event in EVENTS:
            entries = hooks.setdefault(event, [])
            if not isinstance(entries, list):
                raise ValueError('hook entries must be lists')
            entry = {'hooks': [{'type': 'command', 'command': hook_command(), 'timeout': 5}]}
            if event in EVENTS[1:4]:
                entry['matcher'] = '.*'
            entries.append(entry)
        installed = canonical(config) + b'\n'
        settings.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Persist the exact bytes before changing settings; interrupted installs can resume.
        atomic(directory / 'settings.backup', original)
        atomic(journal, canonical({'path': str(settings), 'existed': existed, 'mode': mode,
                                  'original': base64.b64encode(original).decode(),
                                  'installed': base64.b64encode(installed).decode()}))
        atomic(settings, installed, mode)
    return 'installed; exact backup retained locally'


def uninstall():
    directory = root()
    if not directory.exists():
        return 'not installed'
    private_dir(directory)
    with locked(directory / 'install.lock', write=True):
        journal = directory / 'installation.json'
        if not journal.exists():
            return 'not installed'
        prior = parse(read_private(journal))
        settings = settings_path()
        if str(settings) != prior['path']:
            raise ValueError('installation belongs to a different settings path')
        current = read_private(settings) if settings.exists() else None
        original = base64.b64decode(prior['original']) if prior['existed'] else None
        installed = base64.b64decode(prior['installed'])
        mode = settings.stat().st_mode & 0o777 if current is not None else None
        restored = current == installed and mode == prior['mode']
        if restored:
            if prior['existed']:
                atomic(settings, original, prior['mode'])
            else:
                settings.unlink()
        elif current is not None and current != original:
            config = parse(current)
            if not isinstance(config, dict) or not isinstance(config.get('hooks', {}), dict):
                raise ValueError('settings changed; hooks structure is ambiguous')
            original_config = parse(original) if prior['existed'] else {}
            original_hooks = original_config.get('hooks', {})
            installed_hooks = parse(installed)['hooks']
            hooks = config.get('hooks', {})
            removed = False
            for event in EVENTS:
                entries = hooks.get(event, [])
                before = original_hooks.get(event, [])
                if not isinstance(entries, list):
                    raise ValueError('settings changed; hook entries are ambiguous')
                if entries == before:
                    continue
                added = installed_hooks[event][-1]
                if entries == installed_hooks[event]:
                    entries.pop()
                elif added not in before and entries.count(added) == 1:
                    entries.remove(added)
                else:
                    raise ValueError('settings changed; recorder hook ownership is ambiguous')
                removed = True
                if not entries and event not in original_hooks:
                    del hooks[event]
            if removed and not hooks and 'hooks' not in original_config:
                config.pop('hooks', None)
            atomic(settings, canonical(config) + b'\n', mode)
        # Retain backup and journal for audit/recovery, outside the active install slot.
        os.replace(journal, directory / ('uninstalled-' + str(time.time_ns()) + '.json'))
    result = 'original settings restored' if restored else 'later settings preserved'
    return 'uninstalled; ' + result + '; recordings and backup retained'
