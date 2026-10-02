"""Deterministic serialization and strict elementary validation."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from corpustrail.errors import ContractError


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def content_hash(value: Any) -> str:
    return digest_bytes(canonical(value).encode("utf-8"))


def identifier(prefix: str, value: Any) -> str:
    return prefix + ":" + content_hash(value).removeprefix("sha256:")


def text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ContractError(f"{name} must be non-empty text without NUL")


def sha256(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ContractError("expected a SHA-256 content identifier")


def timestamp(value: str) -> None:
    text(value, "timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ContractError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError("timestamp must include a timezone")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative_path(value: str) -> None:
    text(value, "project path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
        raise ContractError("project paths must be confined POSIX-relative paths")
    if value == "." or str(path) != value:
        raise ContractError("project paths must be normalized, non-root paths")


def confined(root: Path, value: str) -> Path:
    relative_path(value)
    result = (root / value).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ContractError("project path escapes through a symbolic link")
    return result
