"""Append-only synthetic connectivity diagnostics, separate from scientific runs."""
from dataclasses import asdict
import json
import os

from corpustrail import __version__
from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.values import ContractError, canonical, content_hash, identifier, text, timestamp
from .contracts import ModelResponse, safe_data


def history(service, run_id):
    result = []
    with connection(service.project.database_path) as db:
        for row in db.execute('SELECT * FROM ct_model_connection_events WHERE run_id=? ORDER BY sequence', (run_id,)):
            envelope = json.loads(row['payload_json'])
            if (content_hash(envelope) != row['content_sha256']
                    or identifier('model-connection-event', envelope) != row['event_id']
                    or any(envelope[k] != row[k] for k in ('kind', 'run_id', 'config_event_id'))):
                raise ContractError('connection diagnostic provenance is corrupt')
            result.append({'event_id': row['event_id'], **envelope})
    return result


def _record(service, db, kind, plan, payload):
    envelope = {'kind': kind, 'run_id': plan['run_id'], 'config_event_id': plan['config_event_id'], 'payload': payload}
    safe_data(envelope, secrets=service._secrets())
    db.execute('INSERT INTO ct_model_connection_events (event_id,kind,run_id,config_event_id,payload_json,content_sha256) VALUES (?,?,?,?,?,?)',
        (identifier('model-connection-event', envelope), kind, plan['run_id'], plan['config_event_id'],
         canonical(envelope), content_hash(envelope)))


def test_connection(service, workflow_id, *, run_id, confirm_external, clock):
    """Never reads candidate evidence. Synthetic transfer approval is NOT evidence consent."""
    text(run_id, 'connection run ID')
    config = service._config(workflow_id)
    adapter = service.registry.resolve(config.adapter, configuration=config)
    if ('connection_test/v1' not in adapter.info.capabilities
            or not callable(getattr(adapter, 'connection_request', None))
            or not callable(getattr(adapter, 'test_connection', None))):
        raise ContractError('selected adapter does not support synthetic connection tests')
    if adapter.info.data_leaves_machine and confirm_external is not True:
        raise ContractError('remote connection test requires --confirm-external; synthetic payload only, no paper evidence')
    request = adapter.connection_request()
    plan = {'run_id': run_id, 'workflow_id': workflow_id, 'configuration': asdict(config),
            'config_event_id': service.project.configuration_history()[-1]['event_id'],
            'adapter': asdict(adapter.info), 'request': request, 'request_sha256': content_hash(request),
            'evidence_types': [], 'purpose': 'synthetic_connection_test_only',
            'external_synthetic_transfer_approved': adapter.info.data_leaves_machine and confirm_external is True,
            'external_evidence_transfer_authorized': False, 'software_version': __version__}
    plan = json.loads(canonical(plan))
    safe_data(plan, secrets=service._secrets())
    prior = history(service, run_id)
    if prior:
        if prior[0]['payload']['plan'] != plan:
            raise ContractError('connection run ID belongs to a different configuration/request')
        complete = [e for e in prior if e['kind'] == 'complete']
        if complete:
            return complete[0]['payload']
        raise ContractError('interrupted connection test; use a new explicit run ID, no automatic retry')
    at = clock(); timestamp(at)
    with connection(service.project.database_path, write=True) as db:
        if latest_config(db)[0] != plan['config_event_id']:
            raise ContractError('configuration changed before connection test')
        if db.execute('SELECT 1 FROM ct_model_connection_events WHERE run_id=?', (run_id,)).fetchone():
            raise ContractError('connection run already reserved')
        _record(service, db, 'started', plan, {'plan': plan, 'started_at': at})
    credential = os.environ.get(config.credential_env) if config.credential_env else None
    response = None; failure = None
    if (config.credential_env or adapter.info.credentials_required) and not credential:
        failure = 'missing_credentials'
    else:
        try:
            response = adapter.test_connection(request, credential=credential)
            if not isinstance(response, ModelResponse):
                raise ContractError('invalid response contract')
            response = response.to_dict()
            safe_data(response, secrets=service._secrets())
            if len(canonical(response).encode('utf-8')) > 2 * 1024 * 1024:
                raise ContractError('bounded diagnostic exceeded')
            if json.loads(canonical(asdict(adapter.info))) != plan['adapter']:
                raise ContractError('adapter changed during connection test')
            failure = response['failure']
            # Never persist arbitrary completion text or a scientific claim here.
            response.pop('output')
        except Exception:
            response = None; failure = 'unsafe_or_invalid_diagnostic'
    at = clock(); timestamp(at)
    result = {'run_id': run_id, 'status': 'failed' if failure else 'succeeded', 'failure': failure,
              'completed_at': at, 'response': response, 'request_sha256': plan['request_sha256'],
              'configured_model': config.model, 'adapter': plan['adapter'],
              'adapter_configuration': config.adapter_configuration, 'assertion_ids': [],
              'external_evidence_transfer_authorized': False, 'production_effect': 'none'}
    result = json.loads(canonical(result))
    safe_data(result, secrets=service._secrets())
    with connection(service.project.database_path, write=True) as db:
        _record(service, db, 'complete', plan, result)
    return result
