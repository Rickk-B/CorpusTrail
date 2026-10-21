"""Explicit installed engines only; no discovery, downloads or fallback."""
from corpustrail._internal.values import ContractError, content_hash
from .contracts import EngineDescription


class EngineRegistry:
    def __init__(self): self._engines = {}

    def register(self, engine):
        info = engine.describe()
        if not isinstance(info, EngineDescription): raise ContractError('typed engine description required')
        info.to_dict()
        key = (info.engine_id, info.version)
        if key in self._engines: raise ContractError('engine identity/version already registered')
        if not callable(getattr(engine, 'prepare', None)) or not callable(getattr(engine, 'assess', None)):
            raise ContractError('engine must implement prepare and assess')
        self._engines[key] = (engine, content_hash(info.to_dict()))

    def get(self, engine_id, version):
        try: engine, expected = self._engines[(engine_id, version)]
        except KeyError as exc: raise ContractError('assessment engine is not installed; no automatic fallback') from exc
        info = engine.describe()
        if not isinstance(info, EngineDescription) or content_hash(info.to_dict()) != expected:
            raise ContractError('registered engine identity/capabilities changed; use a new version')
        return engine, info.to_dict()

    def describe(self): return [self.get(*key)[1] for key in sorted(self._engines)]
