"""Non-authoritative versioned reference labels and frozen context selection."""
from .service import ReferenceService
from .contracts import ContextStrategy,DerivedDependency

__all__ = ['ReferenceService','ContextStrategy','DerivedDependency']
