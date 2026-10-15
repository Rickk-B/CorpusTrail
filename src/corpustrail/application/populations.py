"""Thin bounded DTOs over the authoritative population service; no file imports."""
from pathlib import Path
import re

from corpustrail._internal.database import connection
from corpustrail._internal.pipeline import events_in_connection
from corpustrail._internal.values import ContractError
from corpustrail.populations.contracts import command_id, page
from corpustrail.project import Project
from .project_use import no_links
from .projects import ProjectCommandError

SCHEMA = 'corpustrail-local-populations/v1'


def version_handle(handle):
    if not isinstance(handle, str) or not re.fullmatch('[0-9a-f]{64}', handle):
        raise ContractError('choose a saved population version')
    return 'population-version:' + handle


class PopulationController:
    def configuration(self, project, *, offset=0, limit=20, cutoff=None):
        page(offset, limit)
        with connection(project.database_path) as db:
            if cutoff is None:
                cutoff = db.execute('SELECT COALESCE(MAX(sequence),0) FROM ct_pipeline_events').fetchone()[0]
            if type(cutoff) is not int or cutoff < 0:
                raise ContractError('invalid discovery source cutoff')
            rows = db.execute("SELECT scope_id FROM ct_pipeline_events WHERE kind='discovery_complete' AND sequence<=? ORDER BY sequence DESC LIMIT ? OFFSET ?",
                (cutoff, limit + 1, offset)).fetchall()
            sources = []
            for row in rows[:limit]:
                plans = events_in_connection(db, scope_id=row[0], kind='discovery_plan')
                if not plans:
                    continue
                plan = plans[0]['payload']
                sources.append({'kind': 'discovery', 'run_id': row[0], 'provider': plan['provider'],
                    'query': plan['query'], 'created_at': plan['created_at']})
        return {'schema': SCHEMA, 'available': project.populations.ready(), 'discovery_sources': sources,
            'cutoff': cutoff, 'next_offset': offset + limit if len(rows) > limit else None,
            'production_imports_available': False}

    def command(self, project, action, body):
        try:
            if action == 'upgrade':
                if set(body) != {'request_id', 'confirm_backup'} or body['confirm_backup'] is not True:
                    raise ContractError('explicitly confirm the backed-up population storage upgrade')
                command_id(body['request_id'])
                if project.populations.ready():
                    return {'schema': SCHEMA, 'available': True, 'already_enabled': True}
                no_links(project.root)
                relative = project.config.data_directory + '/population-upgrades/' + body['request_id'] + '.sqlite3'
                no_links(project.root / Path(relative), missing=True)
                Project.upgrade(project.root, backup=relative)
                return {'schema': SCHEMA, 'available': True, 'backup_created': True}
            if action == 'verify':
                if set(body) != {'handle'}:
                    raise ContractError('choose a version to verify')
                return {'schema': SCHEMA, **project.populations.verify(version_handle(body['handle']))}
            fields = {'request_id', 'name', 'actor', 'sources', 'parent'}
            if action == 'create':
                fields |= {'expected_preview_sha256', 'accept_unresolved'}
            elif action != 'preview':
                raise ContractError('unsupported population operation')
            if set(body) != fields:
                raise ContractError('unsupported population fields')
            result = getattr(project.populations, action)(**body)
            return {'schema': SCHEMA, 'population': result}
        except ContractError as exc:
            raise ProjectCommandError(str(exc), code='population_conflict', status=409) from exc
