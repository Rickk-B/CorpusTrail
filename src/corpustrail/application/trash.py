"""Whole-project, recoverable removal. No record cleanup or delete fallback."""
from dataclasses import dataclass
import hashlib
import json
import os
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import secrets
import stat
import sys
import time

from corpustrail.project.service import BOOTSTRAP
from .project_use import acquire_project_use, directory_identity, no_links, ProjectUseError
from .projects import ProjectCommandError, _folder, _safe_path

SCHEMA = 'corpustrail-project-trash/v1'
PYOBJC_VERSION = '12.2.2'


@dataclass(frozen=True)
class TrashResult:
    status: str
    destination: Path | None = None
    diagnostic: str | None = None


class MacOSTrash:
    """Lazy Foundation import; a capability check never loads macOS bindings."""

    def capability(self):
        if sys.platform != 'darwin':
            return {'available': False, 'reason': 'Move to Trash is currently available only on macOS.'}
        try:
            ready = all(version(name) == PYOBJC_VERSION for name in ('pyobjc-framework-Cocoa', 'pyobjc-core'))
        except PackageNotFoundError:
            ready = False
        return {'available': ready, 'reason': '' if ready else
                'Install this wheel with the optional macos-trash extra in your CorpusTrail environment. Normal project use does not need it.'}

    def move(self, path):
        if not self.capability()['available']:
            return TrashResult('failed', diagnostic='trash_unavailable')
        try:
            import objc
            from Foundation import NSFileManager, NSURL, NSURLVolumeIsLocalKey
            with objc.autorelease_pool():
                source = NSURL.fileURLWithPath_(str(path))
                local_ok, local, _ = source.getResourceValue_forKey_error_(None, NSURLVolumeIsLocalKey, None)
                if not local_ok or local is None:
                    return TrashResult('failed', diagnostic='local_storage_unknown')
                if not bool(local):
                    return TrashResult('failed', diagnostic='nonlocal_storage')
                manager = NSFileManager.defaultManager()
                # The NSURL resource property may be unavailable for local items.
                # Use the documented Boolean item check, not nil-as-false inference.
                cloud = manager.isUbiquitousItemAtURL_(source)
                if cloud is None:
                    return TrashResult('failed', diagnostic='cloud_storage_unknown')
                if bool(cloud):
                    return TrashResult('failed', diagnostic='cloud_storage')
                ok, destination, error = manager.trashItemAtURL_resultingItemURL_error_(
                    source, None, None)
                result_path = Path(str(destination.path())) if destination is not None and destination.isFileURL() else None
                code = 'native_' + str(int(error.code())) if error is not None else None
                return TrashResult('moved' if ok else 'failed', result_path, code)
        except Exception:
            # Native messages may contain private paths. Never expose their text.
            return TrashResult('uncertain', diagnostic='native_exception')


def _sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _inventory(root):
    """Tree identity/metadata signature; no symlink targets or article text read."""
    rows = []
    def visit(directory):
        no_links(directory)
        with os.scandir(directory) as listing:
            entries = sorted(listing, key=lambda entry: entry.name)
        for entry in entries:
            path = Path(entry.path); info = entry.stat(follow_symlinks=False)
            row = [str(path.relative_to(root)), info.st_mode, info.st_dev, info.st_ino]
            if stat.S_ISDIR(info.st_mode):
                rows.append(row); visit(path)
            elif stat.S_ISREG(info.st_mode):
                rows.append(row + [info.st_size, info.st_mtime_ns, info.st_ctime_ns])
            elif stat.S_ISLNK(info.st_mode):
                rows.append(row + [os.readlink(path)])
            else:
                raise ProjectCommandError('This folder contains unsupported special filesystem entries; nothing was removed.')
    visit(root)
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()


class ProjectRemoval:
    """Session-memory confirmations, never a persistent scientific registry.

Caller holds the controller mutex. Native mutation additionally needs exclusive
kernel use, exact snapshot validation, then immediate location revalidation.
"""

    def __init__(self, controller, backend=None):
        self.controller = controller
        self.backend = backend or MacOSTrash()
        self.tokens = {}
        self.uncertain = set()

    def _target(self, handle):
        if not isinstance(handle, str) or handle not in self.controller._registered:
            raise ProjectCommandError('Select a project from Projects.', code='project_required', status=409)
        path = _safe_path(self.controller._registered[handle])
        root = _safe_path(self.controller.root)
        if path.parent != root or path == root:
            raise ProjectCommandError('Only projects directly inside the allowed projects location can be moved to Trash.')
        _folder(path.name)
        import corpustrail
        software = Path(corpustrail.__file__).resolve()
        if path in software.parents or (path / '.git').exists():
            raise ProjectCommandError('Software and source repositories cannot be removed as research projects.')
        if handle == self.controller.active_handle:
            raise ProjectCommandError('Close this project before moving it to Trash.', code='project_busy', status=409)
        if handle in self.uncertain:
            raise ProjectCommandError('The earlier result is uncertain. Inspect the original location and Trash; do not retry blindly.',
                                      code='trash_uncertain', status=409)
        return path

    def _snapshot(self, path):
        no_links(path)
        project = self.controller._open_leased(path)  # Caller already holds use.
        config = project.config
        bootstrap, db = _safe_path(path / BOOTSTRAP), _safe_path(project.database_path)
        db_info = db.stat()
        return {'identity': directory_identity(path), 'root_identity': directory_identity(self.controller.root),
                'project_id': config.project_id, 'name': config.name,
                'revision': project.configuration_history()[-1]['event_id'], 'database': config.database,
                'bootstrap_sha256': _sha(bootstrap), 'database_sha256': _sha(db),
                'database_identity': (db_info.st_dev, db_info.st_ino),
                'database_state': (db_info.st_size, db_info.st_mtime_ns, db_info.st_ctime_ns), 'tree_signature': _inventory(path)}

    def eligibility(self, handle):
        capability = self.backend.capability()
        if not capability['available']:
            return capability
        try:
            path = self._target(handle)
            with acquire_project_use(path, exclusive=True):
                self.controller._open_leased(path)
            return {'available': True, 'reason': ''}
        except (ProjectUseError, ProjectCommandError, OSError) as exc:
            return {'available': False, 'reason': str(exc) if isinstance(exc, (ProjectUseError, ProjectCommandError)) else
                    'Project is missing or unavailable. Refresh Projects.'}

    def prepare(self, handle):
        if not self.backend.capability()['available']:
            raise ProjectCommandError(self.backend.capability()['reason'], code='trash_unavailable', status=409)
        path = self._target(handle)
        try:
            with acquire_project_use(path, exclusive=True):
                snapshot = self._snapshot(path)
        except ProjectUseError as exc:
            raise ProjectCommandError(str(exc), code='project_busy', status=409) from exc
        self.tokens = {k: v for k, v in self.tokens.items() if v['expires'] > time.monotonic()}
        if len(self.tokens) >= 256:
            raise ProjectCommandError('Too many pending confirmations. Cancel one or wait before trying again.')
        nonce = secrets.token_urlsafe(32)
        self.tokens[nonce] = {'handle': handle, 'snapshot': snapshot, 'expires': time.monotonic() + 300}
        return {'schema': SCHEMA, 'confirmation': nonce, 'name': snapshot['name'], 'location': str(path),
                'folder': path.name, 'expires_seconds': 300}

    def cancel(self, confirmation):
        if not isinstance(confirmation, str):
            raise ProjectCommandError('Invalid confirmation.')
        self.tokens.pop(confirmation, None)
        return {'schema': SCHEMA, 'status': 'cancelled'}

    def execute(self, confirmation, folder):
        if not isinstance(confirmation, str) or confirmation not in self.tokens:
            raise ProjectCommandError('This confirmation is no longer valid. Refresh Projects.', code='confirmation_expired', status=409)
        token = self.tokens[confirmation]
        handle = token['handle']
        path = self._target(handle)
        if token['expires'] <= time.monotonic():
            self.tokens.pop(confirmation)
            raise ProjectCommandError('Confirmation expired. Select the project again.', status=409)
        if not isinstance(folder, str) or folder != path.name:
            raise ProjectCommandError('Type the exact project folder name to confirm.')
        self.tokens.pop(confirmation)  # One attempt, even if validation/native work fails.
        if not self.backend.capability()['available']:
            raise ProjectCommandError('Native Trash is unavailable. Nothing was removed.', status=409)
        snapshot = token['snapshot']
        try:
            with acquire_project_use(path, exclusive=True) as lease:
                if self._snapshot(path) != snapshot or lease.identity != snapshot['identity']:
                    raise ProjectCommandError('This project changed after confirmation. Refresh and inspect it before continuing.',
                                              code='project_changed', status=409)
                # All validation database connections have closed before the move.
                if self._target(handle) != path or directory_identity(path) != snapshot['identity']:
                    raise ProjectCommandError('The project location changed. Nothing was removed.', status=409)
                try:
                    result = self.backend.move(path)
                except BaseException:
                    result = TrashResult('uncertain', diagnostic='interrupted_native_operation')
                if not isinstance(result, TrashResult):
                    result = TrashResult('uncertain', diagnostic='invalid_native_result')
                success = False
                try:
                    destination = result.destination
                    if result.status == 'moved' and destination is not None and not path.exists() and not path.is_symlink():
                        destination = no_links(destination)
                        moved = self.controller._open_leased(destination)
                        success = (directory_identity(destination) == snapshot['identity']
                            and moved.config.project_id == snapshot['project_id']
                            and _sha(destination / BOOTSTRAP) == snapshot['bootstrap_sha256']
                            and _sha(moved.database_path) == snapshot['database_sha256']
                            and _inventory(destination) == snapshot['tree_signature'])
                    if success:
                        self.controller._registered.pop(handle, None)
                        self.tokens = {k: v for k, v in self.tokens.items() if v['handle'] != handle}
                        self.controller._receipts = {k: v for k, v in self.controller._receipts.items()
                            if not isinstance(v[1], dict) or v[1].get('project_handle') != handle}
                        return {'schema': SCHEMA, 'status': 'moved', 'name': snapshot['name'],
                                'message': snapshot['name'] + ' was moved to Trash. It was verified there; retention is controlled by your computer and you.',
                                'destination': str(destination), 'diagnostic': result.diagnostic}
                    unchanged = path.exists() and self._snapshot(path) == snapshot
                    destination_exists = result.destination is not None and result.destination.exists()
                except Exception:
                    unchanged, destination_exists = False, False
                failed = result.status == 'failed' and unchanged and not destination_exists
                if not failed:
                    self.uncertain.add(handle)
                return {'schema': SCHEMA, 'status': 'failed' if failed else 'uncertain',
                        'message': 'The project could not be moved. Its identity, database and folder inventory were verified unchanged. Check Trash support, permissions and free space.' if failed else
                                   'The result could not be verified. Inspect the original project location and Trash before taking any further action. Do not retry blindly.',
                        'diagnostic': result.diagnostic}
        except ProjectUseError as exc:
            raise ProjectCommandError(str(exc), code='project_busy', status=409) from exc
