"""Optional adapters; imports do not execute external requests."""

def metadata_provider(name):
    from .metadata import MetadataProvider
    return MetadataProvider(name)
