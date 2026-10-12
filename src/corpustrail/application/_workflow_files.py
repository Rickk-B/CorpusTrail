"""Versioned, immutable local workflow receipts, not a second scientific database."""
import json
import os
from pathlib import Path
import tempfile

from corpustrail._internal.values import canonical, content_hash, ContractError
from .project_use import no_links, _acquire_key, directory_identity

SCHEMA = 'corpustrail-local-workflow-record/v1'


def operation_lease(project, purpose):
    return _acquire_key(('local-discovery/v1', directory_identity(project.root), purpose), True)


def location(project, *, family='discovery'):
    # ProjectConfig already validates the relative data directory. Reject all
    # symlink components, including links that stay within the project.
    if family not in {'discovery', 'evidence'}:
        raise ContractError('unsupported local workflow family')
    return no_links(project.root / project.config.data_directory / (family+'-workflows') / 'v1', missing=True)


def read(path):
    path = no_links(path)
    if not path.is_file() or path.stat().st_size > 2_000_000:
        raise ContractError('Workflow record is unavailable or too large.')
    record = json.loads(path.read_text(encoding='utf-8'))
    if set(record) != {'schema', 'payload', 'sha256'} or record['schema'] != SCHEMA or content_hash(record['payload']) != record['sha256']:
        raise ContractError('Workflow record integrity check failed.')
    return record['payload']


def publish(path, payload):
    """Publish complete bytes atomically, without replacing an existing record.

    Hard-link publication is supported by the tested local filesystems. Unsupported
    filesystems fail closed, not via an overwrite or a partially visible final file.
    """
    path = no_links(path, missing=True)
    body = (canonical({'schema': SCHEMA, 'payload': payload, 'sha256': content_hash(payload)}) + '\n').encode('utf-8')
    if len(body) > 2_000_000:
        raise ContractError('Workflow record is too large.')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    no_links(path.parent)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.publishing-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(body); stream.flush(); os.fsync(stream.fileno())
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            if read(path) != payload:
                raise ContractError('Workflow identity already belongs to different content.')
        if path.read_bytes() != body:
            raise ContractError('Workflow publication could not be verified.')
        if os.name == 'posix':
            fd = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try: os.fsync(fd)
            finally: os.close(fd)
    finally:
        # Only our unique staging file, never the immutable destination or project.
        if temporary is not None and temporary.exists():
            temporary.unlink()


def history(project, handle, *, family='discovery'):
    directory = location(project, family=family) / 'events' / handle
    if not directory.exists():
        return []
    no_links(directory)
    result, previous = [], None
    for path in sorted(directory.glob('[0-9]*.json')):
        event = read(path)
        if event['sequence'] != len(result) or event['previous'] != previous:
            raise ContractError('Workflow history is incomplete or changed.')
        previous = content_hash(event)
        result.append(event)
    return result


def append(project, handle, kind, payload, at, *, family='discovery'):
    prior = history(project, handle, family=family)
    event = {'sequence': len(prior), 'previous': content_hash(prior[-1]) if prior else None,
             'kind': kind, 'payload': payload, 'timestamp': at}
    publish(location(project, family=family) / 'events' / handle / f'{len(prior):08d}.json', event)
    return event
