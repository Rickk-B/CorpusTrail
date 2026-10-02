"""Immutable operational events and content-addressed project-local bytes."""

from __future__ import annotations

import json
import os

from .database import connection, latest_config
from .values import ContractError, canonical, confined, digest_bytes, identifier, timestamp


def append(project, kind, scope_id, payload, *, paper_id=None, source_sha256=None,
           config_event_id=None, exclusive=False):
    envelope = {"kind": kind, "scope_id": scope_id, "payload": payload,
                "paper_id": paper_id, "source_sha256": source_sha256,
                "config_event_id": config_event_id or project.configuration_history()[-1]["event_id"]}
    body = canonical(envelope)
    event_id = identifier("pipeline", envelope)
    with connection(project.database_path, write=True) as db:
        if latest_config(db)[0] != envelope["config_event_id"]:
            raise ContractError("configuration changed since planning")
        prior = db.execute("SELECT payload_json FROM ct_pipeline_events WHERE event_id=?", (event_id,)).fetchone()
        if prior and exclusive:
            raise ContractError("attempt already reserved; no implicit network replay")
        if prior and prior[0] != body:
            raise ContractError("pipeline event collision")
        # Ignore only an identical content-addressed event, never another unique scientific key.
        if not prior:
            db.execute("INSERT INTO ct_pipeline_events "
                   "(event_id,kind,scope_id,paper_id,source_sha256,config_event_id,payload_json,content_sha256) "
                   "VALUES (?,?,?,?,?,?,?,?)", (event_id, kind, scope_id, paper_id, source_sha256,
                   envelope["config_event_id"], body, digest_bytes(body.encode("utf-8"))))
    return event_id


def events(project, *, scope_id=None, kind=None, paper_id=None):
    with connection(project.database_path) as db:
        return events_in_connection(db, scope_id=scope_id, kind=kind, paper_id=paper_id)


def events_in_connection(db, *, scope_id=None, kind=None, paper_id=None):
    clauses, parameters = [], []
    for name, value in (("scope_id", scope_id), ("kind", kind), ("paper_id", paper_id)):
        if value is not None:
            clauses.append(name + "=?")
            parameters.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    result = []
    for row in db.execute("SELECT * FROM ct_pipeline_events" + where + " ORDER BY sequence", parameters):
        envelope = json.loads(row["payload_json"])
        if (identifier("pipeline", envelope) != row["event_id"]
                or digest_bytes(row["payload_json"].encode("utf-8")) != row["content_sha256"]
                or any(envelope[key] != row[key] for key in
                       ("kind", "scope_id", "paper_id", "source_sha256", "config_event_id"))):
            raise ContractError("pipeline provenance is corrupt")
        result.append({"event_id": row["event_id"], **envelope})
    return result


def preserve(project, body: bytes, media_type: str, created_at: str) -> str:
    timestamp(created_at)
    if not isinstance(body, bytes) or not isinstance(media_type, str) or not media_type:
        raise ContractError("artifact needs bytes and media type")
    sha = digest_bytes(body)
    relative = project.config.data_directory + "/artifacts/" + sha.split(":")[1]
    path = confined(project.root, relative)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with path.open("xb") as handle:
            os.chmod(path, 0o600)
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        if path.read_bytes() != body:
            raise ContractError("artifact collision; never clobber")
    with connection(project.database_path, write=True) as db:
        prior = db.execute("SELECT byte_size FROM raw_artifacts WHERE sha256=?", (sha,)).fetchone()
        if prior and prior[0] != len(body):
            raise ContractError("artifact registry differs")
        # Media type belongs to each use/representation. Identical bytes can have different declared types.
        db.execute("INSERT OR IGNORE INTO raw_artifacts VALUES (?,?,?,?)", (sha, media_type, len(body), created_at))
        db.execute("INSERT OR IGNORE INTO ct_artifact_files VALUES (?,?)", (sha, relative))
    return sha


def artifact(project, sha):
    with connection(project.database_path) as db:
        return artifact_in_connection(project, db, sha)


def artifact_in_connection(project, db, sha):
    row = db.execute("SELECT relative_path FROM ct_artifact_files WHERE sha256=?", (sha,)).fetchone()
    if row is None:
        raise ContractError("artifact is not locally preserved")
    path = confined(project.root, row[0])
    if digest_bytes(path.read_bytes()) != sha:
        raise ContractError("artifact bytes changed")
    return path
