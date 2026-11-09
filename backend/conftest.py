import os

os.environ.setdefault("RATE_LIMIT_PER_DAY", "0")  # tests start many checks; the limit has its own test


NEEDS_REGISTRY = {"test_full_run_on_real_registry_with_fake_ai_reader", "test_engine_without_ai_still_works_and_says_so"}


def pytest_collection_modifyitems(config, items):
    """Tests that read the real registry are skipped when the database file is not there (e.g. in GitHub CI)."""
    from pathlib import Path

    import adapters
    if Path(adapters.CTG).exists():
        return
    import pytest
    skip = pytest.mark.skip(reason="registry database not present")
    for it in items:
        if it.module.__name__.split(".")[-1] in ("test_real", "test_three_designs") or it.name in NEEDS_REGISTRY:
            it.add_marker(skip)
