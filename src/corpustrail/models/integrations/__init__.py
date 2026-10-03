"""Optional, explicitly selected protocols; no model or endpoint default."""


def register_reference_adapters(registry):
    from .compatible_endpoint import CompatibleEndpointAdapter
    registry.register_factory('compatible-endpoint', CompatibleEndpointAdapter)
