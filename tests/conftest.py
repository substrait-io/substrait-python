import pytest


@pytest.fixture
def find_reference():
    """Return a helper that finds the ``subtree_ordinal`` of the first
    ``ReferenceRel`` reachable through single-input wrapper relations, or None.

    Shared by the ReferenceRel / CTE tests (builders and DataFrame layers)."""

    def _find_reference(rel):
        kind = rel.WhichOneof("rel_type")
        if kind == "reference":
            return rel.reference.subtree_ordinal
        if kind in ("filter", "project", "fetch", "sort"):
            return _find_reference(getattr(rel, kind).input)
        return None

    return _find_reference
