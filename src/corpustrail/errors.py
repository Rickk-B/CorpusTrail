"""Public experimental contract exception."""


class ContractError(ValueError):
    """A standalone contract, stale plan or provenance invariant is invalid."""
