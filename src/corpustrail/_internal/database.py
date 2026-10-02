"""Candidate database transactions; never open/migrate an unmarked database."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager, closing
from importlib import resources
from pathlib import Path

from .values import ContractError, canonical, digest_bytes, identifier


FAMILY = "corpustrail-standalone/v2"


def migrations() -> tuple:
    package = resources.files("corpustrail.operational")
    manifest = json.loads(package.joinpath("schema_manifest.json").read_text(encoding="utf-8"))
    rows = manifest["migrations"]
    names = sorted(x.name for x in package.joinpath("schema").iterdir() if x.name.endswith(".sql"))
    if manifest["schema_family"] != FAMILY or names != [x["name"] for x in rows]:
        raise ContractError("schema resource allowlist differs from frozen manifest")
    if [x["version"] for x in rows] != list(range(1, len(rows) + 1)):
        raise ContractError("schema versions must be contiguous")
    result = []
    for row in rows:
        body = package.joinpath("schema", row["name"]).read_bytes()
        if digest_bytes(body) != row["sha256"]:
            raise ContractError("schema resource hash mismatch")
        result.append((row, body.decode("utf-8")))
    return tuple(result)


@contextmanager
def connection(path: Path, *, write: bool = False):
    if not path.is_file():
        raise ContractError("project database is missing; reads never initialize it")
    db = sqlite3.connect(path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                         uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        try:
            marker = db.execute("SELECT schema_family FROM ct_project_identity WHERE singleton=1").fetchone()
        except sqlite3.DatabaseError as exc:
            raise ContractError("database is not a standalone project; no writes or migration allowed") from exc
        if marker is None or marker[0] != FAMILY:
            raise ContractError("database schema family differs")
        db.execute("PRAGMA foreign_keys=ON")
        if write:
            db.execute("BEGIN IMMEDIATE")
        else:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
        yield db
        if write:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_database(path: Path, config: dict, created_at: str, created_by: str) -> None:
    resources_to_apply = migrations()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Reserve exactly this file. Never connect(create) to an existing database.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    db = sqlite3.connect(path)
    try:
        db.execute("PRAGMA foreign_keys=ON")
        script = "BEGIN IMMEDIATE;\n"
        for row, body in resources_to_apply:
            script += body + "\nINSERT INTO schema_migrations VALUES (" + ",".join(
                str(x) if type(x) is int else "'" + x.replace("'", "''") + "'"
                for x in (row["version"], row["name"], created_at, row["sha256"])) + ");\n"
        # Leave transaction open for parameterized project/bootstrap records.
        db.executescript(script)
        bootstrap_sha = digest_bytes((canonical(config) + "\n").encode("utf-8"))
        db.execute("INSERT INTO ct_project_identity VALUES (1,?,?,?)",
                   (FAMILY, config["project_id"], bootstrap_sha))
        append_config(db, config, None, created_at, created_by)
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ContractError("fresh database has foreign-key violations")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def append_config(db, config, previous_event_id, created_at, created_by) -> str:
    payload = {"schema_version": "corpustrail-config-event/v1", "config": config,
               "previous_event_id": previous_event_id, "created_at": created_at,
               "created_by": created_by}
    event_id = identifier("config", payload)
    db.execute("INSERT INTO ct_project_config_events "
               "(event_id,previous_event_id,payload_json,content_sha256,created_at,created_by) "
               "VALUES (?,?,?,?,?,?)", (event_id, previous_event_id, canonical(payload),
                                        digest_bytes(canonical(payload).encode()), created_at, created_by))
    return event_id


def latest_config(db):
    row = db.execute("SELECT * FROM ct_project_config_events ORDER BY sequence DESC LIMIT 1").fetchone()
    if row is None:
        raise ContractError("project has no configuration event")
    return row["event_id"], json.loads(row["payload_json"])["config"]


def validate_database(db, bootstrap: bytes, project_id: str, *, allow_prefix=False) -> None:
    try:
        marker = db.execute("SELECT * FROM ct_project_identity").fetchone()
        if marker is None or marker["schema_family"] != FAMILY or marker["project_id"] != project_id:
            raise ContractError("database does not belong to this standalone project")
        if marker["bootstrap_sha256"] != digest_bytes(bootstrap):
            raise ContractError("immutable project bootstrap changed")
        rows = [dict(x) for x in db.execute(
            "SELECT version,name,code_sha256 FROM schema_migrations ORDER BY version")]
        expected = [{"version": x[0]["version"], "name": x[0]["name"],
                     "code_sha256": x[0]["sha256"]} for x in migrations()]
        if rows != (expected[:len(rows)] if allow_prefix and len(rows) >= 32 else expected):
            raise ContractError("database schema history differs; no implicit migration")
        previous = None
        for row in db.execute("SELECT * FROM ct_project_config_events ORDER BY sequence"):
            payload = json.loads(row["payload_json"])
            if (identifier("config", payload) != row["event_id"]
                    or digest_bytes(canonical(payload).encode()) != row["content_sha256"]
                    or payload["previous_event_id"] != previous):
                raise ContractError("configuration provenance chain is invalid")
            previous = row["event_id"]
    except sqlite3.DatabaseError as exc:
        raise ContractError("not a compatible standalone project database") from exc


def upgrade_database(path, bootstrap, project_id, backup_path, created_at):
    """Explicit additive upgrade of a marked candidate, with exclusive SQLite backup.

    The writer lock protects the snapshot and migration together. Historical databases
    and altered/missing migration histories fail closed before any backup/write.
    """
    from .values import timestamp
    timestamp(created_at)
    with connection(path, write=True) as db:
        validate_database(db, bootstrap, project_id, allow_prefix=True)
        count = db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        pending = migrations()[count:]
        if not pending:
            raise ContractError("database already current; no backup/upgrade required")
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(backup_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as source, source:
            with closing(sqlite3.connect(backup_path)) as destination, destination:
                source.backup(destination)
        for row, body in pending:
            statement = ""
            for line in body.splitlines(keepends=True):
                statement += line
                if sqlite3.complete_statement(statement):
                    db.execute(statement)
                    statement = ""
            if statement.strip():
                raise ContractError("incomplete migration SQL")
            db.execute("INSERT INTO schema_migrations VALUES (?,?,?,?)",
                       (row["version"], row["name"], created_at, row["sha256"]))
        if count < 34:
            # Old judgments are unchanged. Their availability before upgrade is unknown.
            db.execute("INSERT INTO ct_review_availability SELECT event_id,? FROM ct_review_events",
                       (created_at,))
        validate_database(db, bootstrap, project_id)
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ContractError("upgraded database has foreign-key violations")
