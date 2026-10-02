"""Native parser result contract retained from the historical generic parser API."""

from dataclasses import dataclass
from typing import Any, Mapping


class ParsingError(RuntimeError):
    pass


@dataclass(frozen=True)
class ParserOutput:
    body: str
    representation_kind: str
    structured: bool
    quality: Mapping[str, Any]
    intermediate_bytes: bytes | None = None
    intermediate_kind: str | None = None
    intermediate_media_type: str | None = None
