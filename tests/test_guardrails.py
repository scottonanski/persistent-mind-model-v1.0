import importlib
import pytest


def _import_fails(modname: str):
    with pytest.raises(ImportError):
        importlib.import_module(modname)


def _attr_fails(modname: str, attr: str):
    with pytest.raises((ImportError, AttributeError)):
        mod = importlib.import_module(modname)
        getattr(mod, attr)


def test_struct_semantics_removed():
    _import_fails("pmm.struct_semantics")


def test_introspection_engine_removed():
    _import_fails("pmm.introspection")


def test_commitment_ttl_removed():
    _import_fails("pmm.commitment_ttl")


def test_auto_close_from_reflection_not_on_tracker():
    # If commitments.tracker exists (it does), make sure the AttributeError is raised
    with pytest.raises(AttributeError):
        from pmm.commitments.tracker import CommitmentTracker  # import OK
        getattr(CommitmentTracker, "auto_close_from_reflection")


def test_archive_legacy_commitments_not_on_tracker():
    with pytest.raises(AttributeError):
        from pmm.commitments.tracker import CommitmentTracker
        getattr(CommitmentTracker, "archive_legacy_commitments")
