"""Private per-user OAuth credentials, never a project or export resource.

POSIX: owner-only directory and atomic 0600 files. Windows: DPAPI binds the
serialized secret record to the current Windows user. No credential discovery.
"""
from contextlib import contextmanager, closing
import ctypes
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import uuid

from corpustrail._internal.values import ContractError, canonical
from corpustrail.application.project_use import no_links, _acquire_key


def credential_location():
    home = Path.home()
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', home / 'AppData/Local'))
    elif sys.platform == 'darwin':
        base = home / 'Library/Application Support'
    else:
        base = Path(os.environ.get('XDG_CONFIG_HOME', home / '.config'))
    if not base.is_absolute():
        raise ContractError('The private credential location must be absolute.')
    return base / 'CorpusTrail/chatgpt-credentials-v1'


def _dpapi(body, *, decrypt=False):
    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buf = (ctypes.c_ubyte * len(body)).from_buffer_copy(body)
    source = Blob(len(body), buf); target = Blob()
    crypt = ctypes.windll.crypt32
    crypt.CryptProtectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_wchar_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(Blob)]
    crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(Blob)]
    crypt.CryptProtectData.restype = ctypes.c_int
    crypt.CryptUnprotectData.restype = ctypes.c_int
    ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    ctypes.windll.kernel32.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        ok = crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        ok = crypt.CryptProtectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    if not ok:
        raise ContractError('The private credential store could not be protected for this account.')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


class CredentialStore:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else credential_location()
        if not self.root.is_absolute():
            raise ContractError('Use an absolute private credential location.')
        self.path = self.root / ('credentials.dpapi' if os.name == 'nt' else 'credentials.json')

    def _check(self, path):
        no_links(path)
        info = path.stat()
        if os.name == 'posix' and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
            raise ContractError('ChatGPT credentials require private account-owned files and directories.')
        if info.st_nlink != 1 and path.is_file():
            raise ContractError('Linked credential files are not supported.')

    def read(self):
        no_links(self.root, missing=True)
        if not self.root.exists():
            return {'version': 1, 'host_id': None, 'active': None, 'profiles': {}}
        self._check(self.root)
        if not self.path.exists():
            return {'version': 1, 'host_id': None, 'active': None, 'profiles': {}}
        self._check(self.path)
        if not self.path.is_file() or self.path.stat().st_size > 1_000_000:
            raise ContractError('The private credential record is unavailable.')
        raw = self.path.read_bytes()
        if os.name == 'nt': raw = _dpapi(raw, decrypt=True)
        value = json.loads(raw)
        if value.get('version') != 1 or not isinstance(value.get('profiles'), dict):
            raise ContractError('Unsupported private credential record.')
        return value

    def _write(self, value):
        no_links(self.root, missing=True)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._check(self.root)
        no_links(self.path, missing=True)
        if self.path.exists(): self._check(self.path)
        raw = canonical(value).encode('utf-8')
        if len(raw) > 1_000_000: raise ContractError('Private credential capacity exceeded.')
        if os.name == 'nt': raw = _dpapi(raw)
        staging = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.root, prefix='.credential-', delete=False) as out:
                staging = Path(out.name)
                out.write(raw); out.flush(); os.fsync(out.fileno())
            self._check(staging)
            os.replace(staging, self.path)
            if os.name == 'posix':
                fd = os.open(self.root, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
                try: os.fsync(fd)
                finally: os.close(fd)
        finally:
            # Only a unique file created by this atomic credential write.
            if staging is not None and staging.exists(): staging.unlink()

    @contextmanager
    def transaction(self):
        # Serializes rotating-token updates across processes, not only threads.
        with closing(_acquire_key(('chatgpt-credential-store/v1', str(self.root)), True)):
            value = self.read(); before = canonical(value)
            yield value
            if canonical(value) != before: self._write(value)

    def host_id(self):
        with self.transaction() as state:
            if state['host_id'] is None: state['host_id'] = 'urn:uuid:' + str(uuid.uuid4())
            return state['host_id']
