"""Explicit registration and optional installed entry points; no vendor default."""
from copy import deepcopy
from importlib.metadata import entry_points

from corpustrail._internal.values import ContractError
from .contracts import AdapterInfo, ModelResponse


class AdapterRegistry:
    def __init__(self, adapters=(), *, installed_plugins=False):
        self._adapters = {}
        self._plugins = {}
        if installed_plugins:
            for plugin in entry_points(group='corpustrail.model_adapters'):
                if plugin.name in self._plugins:
                    raise ContractError('duplicate installed model adapter registration')
                self._plugins[plugin.name] = plugin
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter):
        if not isinstance(getattr(adapter, 'info', None), AdapterInfo) or not callable(getattr(adapter, 'invoke', None)):
            raise ContractError('adapter must implement the model contract')
        adapter.info.validate()
        if adapter.info.adapter_id in self._adapters:
            raise ContractError('model adapter identifier already registered')
        self._adapters[adapter.info.adapter_id] = adapter

    def available(self):
        return sorted(set(self._adapters) | set(self._plugins))

    def resolve(self, adapter_id):
        if adapter_id not in self._adapters and adapter_id in self._plugins:
            # Only the explicitly selected installed extension executes trusted code.
            try:
                adapter = self._plugins[adapter_id].load()()
            except Exception:
                raise ContractError('selected adapter could not be loaded; details not logged') from None
            if getattr(getattr(adapter, 'info', None), 'adapter_id', None) != adapter_id:
                raise ContractError('installed adapter identifier mismatch')
            self.register(adapter)
        if adapter_id not in self._adapters:
            raise ContractError('configured model adapter is not installed/registered')
        adapter = self._adapters[adapter_id]
        adapter.info.validate()
        return adapter


class FixtureAdapter:
    """Deterministic local test reference; not a scientific extractor or default."""
    info = AdapterInfo('fixture', 'fixture', 'v1', False)

    def __init__(self, response=None):
        self.response = response or ModelResponse({'claims': []}, 'fixture-model',
                                                  ('fixture-model',), False)
        self.calls = 0

    def invoke(self, request, *, credential=None):
        self.calls += 1
        return deepcopy(self.response)
