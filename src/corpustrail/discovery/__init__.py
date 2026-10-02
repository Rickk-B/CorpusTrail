"""Experimental standalone discovery service and optional adapter contracts."""

from .contracts import CandidateObservation, DiscoveryPage, DiscoveryProvider, RequestSpec, SearchPlan
from .service import DiscoveryService

__all__ = ["SearchPlan", "CandidateObservation", "DiscoveryPage", "DiscoveryProvider", "RequestSpec", "DiscoveryService"]
