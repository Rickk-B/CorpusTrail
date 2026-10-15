"""Immutable candidate versions in the existing scientific SQLite store.

Explicit preparation may walk a selection; normal reads are indexed/paginated.
No title matching, enrollment, evidence verification or membership writes occur.
"""
from dataclasses import asdict
import json

from corpustrail import __version__
from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.pipeline import artifact_in_connection, events_in_connection
from corpustrail._internal.values import ContractError, canonical, content_hash, identifier, now, text, timestamp
from corpustrail.curation.service import membership_in_connection
from .contracts import ImportedSource, POLICY, SCHEMA, command_id, page, version_id


def available(db):
    return db.execute('SELECT 1 FROM schema_migrations WHERE version=38').fetchone() is not None


def require(db):
    if not available(db):
        raise ContractError('Enable population storage with an explicit backed-up project upgrade first.')


def _header(db, vid):
    version_id(vid); require(db)
    row = db.execute('SELECT * FROM ct_population_versions WHERE version_id=?', (vid,)).fetchone()
    if row is None:
        raise ContractError('population version is not in this project')
    data = json.loads(row['payload_json'])
    if (identifier('population-version', data) != vid or data['schema'] != SCHEMA
            or data['project_id'] != db.execute('SELECT project_id FROM ct_project_identity WHERE singleton=1').fetchone()[0]
            or data['population_id'] != row['population_id'] or data['version'] != row['version']
            or data['config_event_id'] != row['config_event_id'] or data['request_id'] != row['request_id']
            or data['request_sha256'] != row['request_sha256']):
        raise ContractError('population header integrity check failed')
    return data


def _checked(body, sha):
    value = json.loads(body)
    if content_hash(value) != sha:
        raise ContractError('population content integrity check failed')
    return value


def _stored(db, vid):
    header = _header(db, vid)
    members = {}
    for row in db.execute('SELECT * FROM ct_population_members WHERE version_id=? ORDER BY paper_id', (vid,)):
        members[row['paper_id']] = {'identity': _checked(row['identity_json'], row['identity_sha256']), 'lineage': {}}
    for row in db.execute('SELECT * FROM ct_population_lineage WHERE version_id=? ORDER BY paper_id,origin_key', (vid,)):
        if row['paper_id'] not in members:
            raise ContractError('population lineage has no member')
        value = _checked(row['payload_json'], row['content_sha256'])
        if identifier('origin', value) != row['origin_key']:
            raise ContractError('population origin identity changed')
        members[row['paper_id']]['lineage'][row['origin_key']] = value
    issues = {}
    for row in db.execute('SELECT * FROM ct_population_issues WHERE version_id=? ORDER BY issue_key', (vid,)):
        value = _checked(row['payload_json'], row['content_sha256'])
        if identifier('population-issue', value) != row['issue_key']:
            raise ContractError('population issue identity changed')
        issues[row['issue_key']] = value
    snapshot = _snapshot(members, issues)
    if any(snapshot[k] != header[k] for k in snapshot):
        raise ContractError('population manifest or counts changed')
    parents = [r[0] for r in db.execute('SELECT parent_id FROM ct_population_parents WHERE version_id=? ORDER BY parent_id', (vid,))]
    if parents != header['parents']:
        raise ContractError('population parent lineage changed')
    return header, members, issues


def _snapshot(members, issues):
    # Canonical order and set union make content independent of input order.
    ordered = {pid: {'identity': value['identity'], 'lineage': sorted(value['lineage'])}
               for pid, value in sorted(members.items())}
    origins = {key: value for member in members.values() for key, value in member['lineage'].items()}
    return {'member_count': len(members), 'lineage_count': sum(len(x['lineage']) for x in members.values()),
        'overlapping_publications': sum(sum(v['kind'] == 'enrolled_observation' for v in x['lineage'].values()) > 1 for x in members.values()),
        'unresolved_count': len(issues), 'members_sha256': content_hash(sorted(members)),
        'manifest_sha256': content_hash({'members': ordered, 'origins': origins, 'issues': issues})}


class PopulationService:
    def __init__(self, project):
        self.project = project

    def ready(self):
        with connection(self.project.database_path) as db:
            return available(db)

    @staticmethod
    def _identity(db, pid):
        row = db.execute('SELECT * FROM paper_entities WHERE paper_id=?', (pid,)).fetchone()
        if row is None or row['identity_state'] != 'active':
            raise ContractError('select an active canonical publication; identity remapping requires a successor population')
        return {'entity': dict(row), 'identifiers': [dict(x) for x in db.execute(
            'SELECT * FROM paper_identifiers WHERE paper_id=? ORDER BY scheme,normalized_value,identifier_id', (pid,))]}

    @staticmethod
    def _observation(db, oid):
        row = db.execute('SELECT * FROM ct_paper_observations WHERE observation_id=?', (oid,)).fetchone()
        if row is None:
            raise ContractError('source observation is not enrolled in this project')
        plan = db.execute('SELECT payload_json FROM ct_enrollment_operations WHERE plan_id=?', (row['plan_id'],)).fetchone()
        if plan is None:
            raise ContractError('source enrollment is missing')
        raw = json.loads(plan[0]); observation = json.loads(row['payload_json'])
        if (identifier('enroll', raw) != row['plan_id'] or identifier('bibliography', raw) != oid
                or raw['paper_id'] != row['paper_id'] or observation != {k: raw[k] for k in ('record', 'source')}
                or raw['source']['source_sha256'] != row['source_sha256']):
            raise ContractError('source observation integrity check failed')
        return row, observation

    def _add(self, db, members, pid, origin):
        if pid not in members:
            members[pid] = {'identity': self._identity(db, pid), 'lineage': {}}
        members[pid]['lineage'][identifier('origin', origin)] = origin

    def _enrolled(self, db, members, oid):
        row, observation = self._observation(db, oid)
        source = observation['source']
        self._add(db, members, row['paper_id'], {'kind': 'enrolled_observation', 'observation_id': oid,
            'observation_sha256': content_hash(observation), 'enrollment_plan_id': row['plan_id'],
            'source_sha256': source['source_sha256'], 'producer_id': source['producer_id'],
            'producer_type': source['producer_type'], 'identity_status': source['identity_status']})

    def _discovery(self, db, members, issues, run):
        text(run, 'discovery run')
        plans = events_in_connection(db, scope_id=run, kind='discovery_plan')
        complete = events_in_connection(db, scope_id=run, kind='discovery_complete')
        if not plans or not complete:
            raise ContractError('select a discovery run with a recorded outcome; running sources cannot be frozen')
        for observation in events_in_connection(db, scope_id=run, kind='candidate_observation'):
            links = events_in_connection(db, scope_id=observation['event_id'], kind='canonical_link')
            if not links:
                failures = events_in_connection(db, scope_id=observation['event_id'], kind='identity_issue')
                issue = {'kind': 'unlinked_discovery_record', 'run_id': run, 'observation_id': observation['event_id'],
                    'observation_sha256': content_hash(observation), 'reason': failures[-1]['payload']['reason'] if failures else 'No canonical publication link at freezing.'}
                issues[identifier('population-issue', issue)] = issue
                continue
            link = links[0]; pid = link['payload']['paper_id']
            enrolled = db.execute('SELECT observation_id FROM ct_paper_observations WHERE plan_id=?',
                (link['payload']['enrollment_plan_id'],)).fetchone()
            if enrolled is None:
                raise ContractError('discovery link has no enrolled source observation')
            self._enrolled(db, members, enrolled[0])
            self._add(db, members, pid, {'kind': 'discovery', 'run_id': run,
                'observation_id': observation['event_id'], 'observation_sha256': content_hash(observation),
                'canonical_link_id': link['event_id'], 'enrollment_observation_id': enrolled[0],
                'provider': observation['payload']['provider'], 'source_sha256': observation['source_sha256']})
        return {'provider': plans[0]['payload']['provider'], 'query': plans[0]['payload']['query'],
            'plan_id': plans[0]['event_id'], 'plan_sha256': content_hash(plans[0]),
            'completion_sha256': content_hash(complete[0])}

    def _current(self, db, members, ids):
        for pid in sorted(set(ids)):
            found = False
            for row in db.execute('SELECT observation_id FROM ct_paper_observations WHERE paper_id=? ORDER BY observation_id', (pid,)):
                self._enrolled(db, members, row[0]); found = True
            if not found:
                raise ContractError('canonical publication has no enrolled bibliographic source')
        # Preserve every contributing run observation, including repeated sightings
        # that use the same provider record/enrollment. Unlinked records are not
        # members of a selection explicitly restricted to canonical publications.
        selected = set(ids)
        for link in events_in_connection(db, kind='canonical_link'):
            if link['paper_id'] not in selected:
                continue
            row = db.execute('SELECT scope_id FROM ct_pipeline_events WHERE event_id=? AND kind=?',
                (link['scope_id'], 'candidate_observation')).fetchone()
            if row is None:
                raise ContractError('canonical source link has no discovery observation')
            # Cache each run once, rather than reparsing it for every paper.
            run = row[0]
            if run not in self._run_cache:
                self._run_cache[run] = {x['event_id']: x for x in events_in_connection(db, scope_id=run, kind='candidate_observation')}
            observation = self._run_cache[run].get(link['scope_id'])
            if observation is None:
                raise ContractError('canonical source lineage differs')
            enrolled = db.execute('SELECT observation_id FROM ct_paper_observations WHERE plan_id=?', (link['payload']['enrollment_plan_id'],)).fetchone()
            if enrolled is None:
                raise ContractError('canonical discovery link has no enrolled source')
            self._add(db, members, link['paper_id'], {'kind': 'discovery', 'run_id': run,
                'observation_id': observation['event_id'], 'observation_sha256': content_hash(observation),
                'canonical_link_id': link['event_id'], 'enrollment_observation_id': enrolled[0],
                'provider': observation['payload']['provider'], 'source_sha256': observation['source_sha256']})

    def _prepare(self, db, *, request_id, name, actor, sources, parent=None, imported=None):
        require(db); command_id(request_id)
        for value, label in ((name, 'population name'), (actor, 'creation attribution')):
            text(value, label)
            if len(value) > 200:
                raise ContractError(label + ' is too long')
        if not isinstance(sources, list) or not 1 <= len(sources) <= 50:
            raise ContractError('select 1–50 source units per operation; existing versions can combine larger collections')
        self._run_cache = {}
        normalized = []
        members, issues, parents = {}, {}, set()
        for spec in sources:
            if not isinstance(spec, dict) or 'kind' not in spec:
                raise ContractError('choose an explicit population source')
            kind = spec['kind']
            if kind in {'all', 'corpus', 'awaiting'} and set(spec) == {'kind'}:
                ids = [r[0] for r in db.execute('SELECT paper_id FROM paper_entities ORDER BY paper_id')]
                if kind != 'all':
                    allowed = {'included'} if kind == 'corpus' else {'not_reviewed', 'unresolved'}
                    ids = [p for p in ids if membership_in_connection(db, p)['state'] in allowed]
                self._current(db, members, ids)
                # Membership-based selection must preserve its actual heads.
                if kind != 'all':
                    heads = {}
                    for pid in ids:
                        state = membership_in_connection(db, pid)
                        heads[pid] = state['current_event_id']
                        self._add(db, members, pid, {'kind': 'membership_selection', 'selection': kind,
                            'state_at_freezing': state['state'], 'membership_head': state['current_event_id']})
                    spec = {**spec, 'selection_heads_sha256': content_hash(heads)}
            elif kind == 'selection' and set(spec) == {'kind', 'paper_ids'}:
                ids = spec['paper_ids']
                if not isinstance(ids, list) or not ids or len(ids) > 500 or any(not isinstance(p, str) for p in ids):
                    raise ContractError('select 1–500 exact papers per selection unit; combine versions for larger selections')
                spec = {'kind': kind, 'paper_ids': sorted(set(ids))}
                self._current(db, members, spec['paper_ids'])
            elif kind == 'discovery' and set(spec) == {'kind', 'run_id'}:
                spec = {**spec, **self._discovery(db, members, issues, spec['run_id'])}
            elif kind == 'version' and set(spec) == {'kind', 'version_id'}:
                vid = version_id(spec['version_id']); source_header, prior, prior_issues = _stored(db, vid); parents.add(vid)
                spec = {**spec, 'name': source_header['name'], 'version': source_header['version'],
                    'manifest_sha256': source_header['manifest_sha256']}
                for pid, value in prior.items():
                    if pid not in members:
                        members[pid] = {'identity': self._identity(db, pid), 'lineage': {}}
                    members[pid]['lineage'].update(value['lineage'])
                issues.update(prior_issues)
            elif kind == 'import_interface' and imported is not None and spec == {'kind': kind}:
                imported.validate(); artifact_in_connection(self.project, db, imported.artifact_sha256)
                for oid in imported.observation_ids:
                    row, observation = self._observation(db, oid)
                    if observation['source']['source_sha256'] != imported.artifact_sha256:
                        raise ContractError('imported-source artifact does not support this observation')
                    self._enrolled(db, members, oid)
                    self._add(db, members, row['paper_id'], {'kind': 'import_interface', 'source_id': imported.source_id,
                        'adapter_id': imported.adapter_id, 'adapter_version': imported.adapter_version,
                        'artifact_sha256': imported.artifact_sha256, 'observation_id': oid})
                spec = {**spec, 'interface': {k: v for k, v in asdict(imported).items() if k != 'observation_ids'},
                    'observation_ids_sha256': content_hash(sorted(imported.observation_ids))}
            else:
                raise ContractError('unsupported population source; production format importers are not implemented')
            normalized.append(spec)
        config, raw = latest_config(db)
        previous = _header(db, parent) if parent else None
        if parent:
            parents.add(parent)
            head = db.execute('SELECT version_id FROM ct_population_versions WHERE population_id=? ORDER BY version DESC LIMIT 1',
                (previous['population_id'],)).fetchone()[0]
            if head != parent:
                raise ContractError('population changed in another operation; inspect the latest version')
        selection = sorted({canonical(x): x for x in normalized}.values(), key=canonical)
        snapshot = _snapshot(members, issues)
        plan = {'schema': SCHEMA, 'policy': POLICY, 'project_id': raw['project_id'], 'name': name, 'actor': actor,
            'config_event_id': config, 'definition_sha256': content_hash({'scope': raw['review']['scope'], 'config_event_id': config}),
            'population_id': previous['population_id'] if previous else identifier('population', {'project': raw['project_id'], 'request_id': request_id}),
            'version': previous['version'] + 1 if previous else 1, 'previous_version': parent,
            'parents': sorted(parents), 'selection': selection, **snapshot}
        return plan, members, issues

    def preview(self, **fields):
        with connection(self.project.database_path) as db:
            plan, _, _ = self._prepare(db, **fields)
            return {**self._public(plan), 'frozen': False, 'preview_sha256': content_hash(plan)}

    def create(self, *, expected_preview_sha256, accept_unresolved=False, created_at=None, imported=None, **fields):
        created_at = created_at or now(); timestamp(created_at)
        if type(accept_unresolved) is not bool:
            raise ContractError('explicit unresolved-source confirmation must be boolean')
        command_id(fields.get('request_id'))
        request = {**fields, 'expected_preview_sha256': expected_preview_sha256, 'accept_unresolved': accept_unresolved,
            'imported': asdict(imported) if imported else None}
        request_sha = content_hash(request)
        with connection(self.project.database_path, write=True) as db:
            require(db)
            replay = db.execute('SELECT version_id,request_sha256 FROM ct_population_versions WHERE request_id=?', (fields['request_id'],)).fetchone()
            if replay:
                if replay['request_sha256'] != request_sha:
                    raise ContractError('population request was already used with different input')
                _stored(db, replay['version_id'])
                return {'version_id': replay['version_id'], **self._public(_header(db, replay['version_id'])), 'replayed': True}
            plan, members, issues = self._prepare(db, imported=imported, **fields)
            if content_hash(plan) != expected_preview_sha256:
                raise ContractError('population sources, configuration or selection changed; preview again')
            if issues and not accept_unresolved:
                raise ContractError('explicitly acknowledge unresolved records; they will not become canonical candidates')
            payload = {**plan, 'created_at': created_at, 'software_version': __version__,
                'unresolved_accepted': accept_unresolved, 'request_sha256': request_sha, 'request_id': fields['request_id']}
            vid = identifier('population-version', payload)
            db.execute('INSERT INTO ct_population_versions(version_id,population_id,version,request_id,request_sha256,payload_json,config_event_id) VALUES (?,?,?,?,?,?,?)',
                (vid, plan['population_id'], plan['version'], fields['request_id'], request_sha, canonical(payload), plan['config_event_id']))
            db.executemany('INSERT INTO ct_population_members VALUES (?,?,?,?)',
                ((vid, pid, canonical(m['identity']), content_hash(m['identity'])) for pid, m in sorted(members.items())))
            db.executemany('INSERT INTO ct_population_lineage VALUES (?,?,?,?,?)',
                ((vid, pid, key, canonical(value), content_hash(value)) for pid, m in sorted(members.items()) for key, value in sorted(m['lineage'].items())))
            db.executemany('INSERT INTO ct_population_issues VALUES (?,?,?,?)',
                ((vid, key, canonical(value), content_hash(value)) for key, value in sorted(issues.items())))
            db.executemany('INSERT INTO ct_population_parents VALUES (?,?)', ((vid, p) for p in plan['parents']))
            return {'version_id': vid, **self._public(payload), 'replayed': False}

    def freeze_import_source(self, source: ImportedSource, **fields):
        """Trusted adapter API only. No HTTP upload, parsing or enrollment occurs."""
        fields = {**fields, 'sources': [{'kind': 'import_interface'}]}
        preview = self.preview(imported=source, **fields)
        return self.create(imported=source, expected_preview_sha256=preview['preview_sha256'], **fields)

    @staticmethod
    def _public(data):
        keys = ('schema', 'policy', 'name', 'actor', 'version', 'population_id', 'previous_version', 'parents',
                'member_count', 'lineage_count', 'overlapping_publications', 'unresolved_count', 'members_sha256',
                'manifest_sha256', 'config_event_id', 'definition_sha256')
        result = {k: data[k] for k in keys}
        result['created_at'] = data.get('created_at')
        # Do not send huge selection/head maps in routine browser responses.
        result['sources'] = [{k: v for k, v in spec.items() if k not in {'paper_ids', 'selection_heads'}} |
            ({'selected_count': len(spec['paper_ids'])} if 'paper_ids' in spec else {}) for spec in data['selection']]
        result['frozen'] = True
        return result

    def versions(self, *, offset=0, limit=20, cutoff=None):
        page(offset, limit)
        with connection(self.project.database_path) as db:
            if not available(db):
                return {'available': False, 'items': [], 'total': 0, 'next_offset': None}
            if cutoff is None:
                cutoff = db.execute('SELECT COALESCE(MAX(sequence),0) FROM ct_population_versions').fetchone()[0]
            if type(cutoff) is not int or cutoff < 0:
                raise ContractError('invalid population list cutoff')
            total = db.execute('SELECT COUNT(*) FROM ct_population_versions WHERE sequence<=?', (cutoff,)).fetchone()[0]
            rows = db.execute('SELECT version_id FROM ct_population_versions WHERE sequence<=? ORDER BY sequence DESC LIMIT ? OFFSET ?', (cutoff, limit, offset))
            return {'available': True, 'items': [{'version_id': r[0], **self._public(_header(db, r[0]))} for r in rows],
                'total': total, 'cutoff': cutoff, 'next_offset': offset + limit if offset + limit < total else None}

    def inspect(self, vid):
        with connection(self.project.database_path) as db:
            return {'version_id': vid, **self._public(_header(db, vid))}

    def verify(self, vid):
        with connection(self.project.database_path) as db:
            data, _, _ = _stored(db, vid)
            return {'version_id': vid, 'verified': True, 'manifest_sha256': data['manifest_sha256']}

    def members(self, vid, *, offset=0, limit=20):
        page(offset, limit)
        with connection(self.project.database_path) as db:
            header = _header(db, vid)
            rows = db.execute('SELECT * FROM ct_population_members WHERE version_id=? ORDER BY paper_id LIMIT ? OFFSET ?', (vid, limit, offset))
            items = []
            for row in rows:
                frozen = _checked(row['identity_json'], row['identity_sha256'])
                metadata = self.project.discovery._metadata(db, row['paper_id'])
                items.append({'paper_id': row['paper_id'], 'handle': row['paper_id'].split(':')[1],
                    'title': metadata['fields']['title'], 'identity_snapshot': frozen,
                    'lineage_count': db.execute('SELECT COUNT(*) FROM ct_population_lineage WHERE version_id=? AND paper_id=?', (vid, row['paper_id'])).fetchone()[0]})
            return {'items': items, 'total': header['member_count'], 'next_offset': offset + limit if offset + limit < header['member_count'] else None}

    def lineage(self, vid, *, offset=0, limit=20):
        page(offset, limit)
        with connection(self.project.database_path) as db:
            header = _header(db, vid)
            rows = db.execute('SELECT * FROM ct_population_lineage WHERE version_id=? ORDER BY paper_id,origin_key LIMIT ? OFFSET ?', (vid, limit, offset))
            return {'items': [{'paper_id': r['paper_id'], **_checked(r['payload_json'], r['content_sha256'])} for r in rows],
                'total': header['lineage_count'], 'next_offset': offset + limit if offset + limit < header['lineage_count'] else None}

    def issues(self, vid, *, offset=0, limit=20):
        page(offset, limit)
        with connection(self.project.database_path) as db:
            header = _header(db, vid)
            rows = db.execute('SELECT * FROM ct_population_issues WHERE version_id=? ORDER BY issue_key LIMIT ? OFFSET ?', (vid, limit, offset))
            return {'items': [_checked(r['payload_json'], r['content_sha256']) for r in rows], 'total': header['unresolved_count'],
                'next_offset': offset + limit if offset + limit < header['unresolved_count'] else None}

    def review_ids(self, db, vid):
        _, members, _ = _stored(db, vid)
        for pid in members:
            self._identity(db, pid)  # Never silently remap a retired historical ID.
        return sorted(members)

    def bind_review(self, db, vid, session):
        header, members, _ = _stored(db, vid)
        row = db.execute('SELECT payload_json FROM ct_review_sessions WHERE session_id=?', (session,)).fetchone()
        packet = json.loads(row[0])
        if packet['population_sha256'] != content_hash(sorted(members)):
            raise ContractError('review packet differs from the selected population')
        value = {'schema': 'corpustrail-review-population-link/v1', 'session_id': session, 'version_id': vid,
            'manifest_sha256': header['manifest_sha256'], 'members_sha256': header['members_sha256']}
        db.execute('INSERT INTO ct_population_review_links VALUES (?,?,?,?)', (session, vid, canonical(value), content_hash(value)))
        return {'version_id': vid, 'version': header['version'], 'frozen': True,
                'manifest_sha256': header['manifest_sha256']}

    def review_link(self, db, session):
        if not available(db):
            return None
        row = db.execute('SELECT * FROM ct_population_review_links WHERE session_id=?', (session,)).fetchone()
        if row is None:
            created = db.execute('SELECT payload_json FROM ct_review_session_events WHERE session_id=? ORDER BY sequence LIMIT 1', (session,)).fetchone()
            if created and json.loads(created[0]).get('result', {}).get('candidate_population') is not None:
                raise ContractError('immutable session population link is missing')
            return None
        value = _checked(row['payload_json'], row['content_sha256']); header = _header(db, row['version_id'])
        packet = json.loads(db.execute('SELECT payload_json FROM ct_review_sessions WHERE session_id=?', (session,)).fetchone()[0])
        if (value['session_id'] != session or value['version_id'] != row['version_id']
                or value['manifest_sha256'] != header['manifest_sha256'] or value['members_sha256'] != packet['population_sha256']):
            raise ContractError('review population provenance differs')
        # Deliberately omit source names/methods from method-blind review DTOs.
        result = {'version_id': row['version_id'], 'version': header['version'], 'frozen': True,
                  'manifest_sha256': header['manifest_sha256']}
        created = db.execute('SELECT payload_json FROM ct_review_session_events WHERE session_id=? ORDER BY sequence LIMIT 1', (session,)).fetchone()
        if created is None or json.loads(created[0]).get('result', {}).get('candidate_population') != result:
            raise ContractError('population link differs from the immutable session creation receipt')
        return result
