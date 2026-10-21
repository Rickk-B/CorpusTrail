"""Kernel lifecycle leases outside research folders, not scientific transactions.

Participating same-user/same-machine clients only. Never unlink live anchors.
File existence/PID records are not locks; the OS releases leases on process exit.
"""
from contextlib import contextmanager
import ctypes
from functools import wraps
import hashlib
import os
from pathlib import Path
import stat
import sys
import threading
import weakref

from corpustrail.errors import ContractError


class ProjectUseError(ContractError):
    """Redacted lifecycle failure."""


class ProjectBusy(ProjectUseError):
    pass


_mutex = threading.RLock()
_held = {}


def lock_directory():
    if os.name == 'nt':
        from ctypes import wintypes
        shell = ctypes.WinDLL('shell32', use_last_error=True)
        shell.SHGetFolderPathW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR]
        shell.SHGetFolderPathW.restype = ctypes.c_long
        buffer = ctypes.create_unicode_buffer(32768)
        if shell.SHGetFolderPathW(None, 0x1C, None, 0, buffer) != 0 or not buffer.value:
            raise ProjectUseError('Windows could not locate project-use protection.')
        return Path(buffer.value) / 'CorpusTrail' / 'project-locks'
    if os.name == 'posix' and (sys.platform == 'darwin' or sys.platform.startswith('linux')):
        import pwd
        home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        return home / ('Library/Application Support' if sys.platform == 'darwin' else '.local/state') / 'CorpusTrail/project-locks'
    raise ProjectUseError('Project-use protection is unavailable on this platform.')


def no_links(path, *, missing=False):
    path = Path(path).absolute()
    for component in (*reversed(path.parents), path):
        try:
            info = component.lstat()
        except FileNotFoundError:
            if missing:
                continue
            raise
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ProjectUseError('Symbolic-link or reparse locations are not supported.')
    return path


def directory_identity(path):
    info = no_links(path).stat()
    if not stat.S_ISDIR(info.st_mode) or not info.st_ino:
        raise ProjectUseError('The project location cannot be locked safely.')
    return info.st_dev, info.st_ino


def _anchor(key):
    directory = lock_directory()
    no_links(directory, missing=True)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    no_links(directory)
    info = directory.stat()
    if os.name == 'posix' and (info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise ProjectUseError('The lock location must be private to your account.')
    path = directory / (hashlib.sha256(('project-use/v1:' + repr(key)).encode('utf-8')).hexdigest() + '.lock')
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0), 0o600)
    try:
        os.set_inheritable(fd, False)
        info, actual = os.fstat(fd), path.lstat()
        if (not stat.S_ISREG(actual.st_mode) or getattr(actual, 'st_file_attributes', 0) & 0x400 or info.st_nlink != 1
                or (info.st_dev, info.st_ino) != (actual.st_dev, actual.st_ino)):
            raise ProjectUseError('The lock file cannot be used safely.')
        if os.name == 'posix' and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ProjectUseError('The lock file must be private to your account.')
        return fd
    except BaseException:
        os.close(fd)
        raise


def _kernel_lock(fd, exclusive):
    if os.name == 'posix' and (sys.platform == 'darwin' or sys.platform.startswith('linux')):
        import fcntl
        try:
            fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProjectBusy('This project is in use. Close its other windows or wait for operations to finish.') from exc
        return None
    if os.name == 'nt':
        import msvcrt
        from ctypes import wintypes
        class Overlapped(ctypes.Structure):
            _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                        ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD), ('hEvent', wintypes.HANDLE)]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                     wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped)]
        kernel.LockFileEx.restype = wintypes.BOOL
        overlap = Overlapped()
        if not kernel.LockFileEx(msvcrt.get_osfhandle(fd), 1 | (2 if exclusive else 0), 0, 1, 0, ctypes.byref(overlap)):
            if ctypes.get_last_error() == 33:
                raise ProjectBusy('This project is in use. Close its other windows or wait for operations to finish.')
            raise ProjectUseError('Windows could not establish project-use protection.')
        return overlap
    raise ProjectUseError('Project-use protection is unavailable on this platform.')


def _release(key, entry, pid):
    if pid != os.getpid():
        return
    with _mutex:
        if _held.get(key) is not entry:
            return
        entry['count'] -= 1
        if not entry['count']:
            _held.pop(key)
            os.close(entry['fd'])


class _Lease:
    def __init__(self, key, entry):
        self.release = weakref.finalize(self, _release, key, entry, os.getpid())
    def close(self):
        self.release()


def _acquire_key(key, exclusive):
    with _mutex:
        entry = _held.get(key)
        if entry is not None:
            if exclusive or entry['exclusive']:
                raise ProjectBusy('This project is already in use; lock upgrades are not allowed.')
            entry['count'] += 1
        else:
            fd = _anchor(key)
            try:
                native = _kernel_lock(fd, exclusive)
            except BaseException:
                os.close(fd)
                raise
            entry = {'fd': fd, 'native': native, 'exclusive': exclusive, 'count': 1}
            _held[key] = entry
        return _Lease(key, entry)


class ProjectLease:
    def __init__(self, identity, leases):
        self.identity, self._leases = identity, leases
    def close(self):
        for lease in reversed(self._leases):
            lease.close()
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.close()


def acquire_project_use(path, *, exclusive=False, _creation=False):
    leases = []
    try:
        path = no_links(path, missing=_creation).resolve()
        identity = None if _creation and not path.exists() else directory_identity(path)
        directory = lock_directory().absolute()
        if directory == path or path in directory.parents:
            raise ProjectUseError('Project-use protection must be stored outside the project.')
        leases.append(_acquire_key(('location', os.path.normcase(str(path))), exclusive))
        if identity is not None:
            leases.append(_acquire_key(('directory', *identity), exclusive))
            if directory_identity(path) != identity:
                raise ProjectUseError('The project location changed. Refresh before continuing.')
        elif path.exists():
            raise ProjectUseError('The project location changed. Refresh before continuing.')
        return ProjectLease(identity, leases)
    except BaseException as exc:
        for lease in reversed(leases):
            lease.close()
        if not isinstance(exc, ProjectUseError) and isinstance(exc, (OSError, ValueError)):
            raise ProjectUseError('The project is unavailable or cannot be locked safely. Nothing was removed.') from exc
        raise


@contextmanager
def project_use(path):
    with acquire_project_use(path) as lease:
        yield lease


@contextmanager
def operation_use(path, operation):
    """One process per named operation, while retaining the shared project lease.

    Anchors use the existing private OS lock directory and are never unlinked.
    A dead process releases its kernel lock; it does not erase durable progress.
    """
    if not isinstance(operation, str) or not operation or len(operation) > 200:
        raise ProjectUseError('A bounded operation identity is required.')
    with project_use(path):
        lease = _acquire_key(('operation', *directory_identity(path), operation), True)
        try:
            yield
        finally:
            lease.close()


@contextmanager
def creation_use(path):
    with acquire_project_use(path, _creation=True) as lease:
        yield lease


def _after_fork():
    global _mutex
    for entry in _held.values():
        os.close(entry['fd'])
    _held.clear()
    _mutex = threading.RLock()


if hasattr(os, 'register_at_fork'):
    os.register_at_fork(after_in_child=_after_fork)


def leased_server_factory(factory):
    @wraps(factory)
    def guarded(project=None, *args, **kwargs):
        controller = kwargs.get('controller')
        lease = acquire_project_use(project.root) if project is not None else None
        try:
            server = factory(project, *args, **kwargs)
        except BaseException:
            if lease:
                lease.close()
            raise
        def release_use():
            if lease:
                lease.close()
            if controller is not None:
                controller.close()
        release = weakref.finalize(server, release_use)
        close = server.server_close
        def server_close():
            try:
                close()
            finally:
                release()
        server.server_close = server_close
        return server
    return guarded
