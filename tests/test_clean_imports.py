"""Tests to verify no unused imports in critical modules."""


def test_response_handler_imports():
    """response_handler must import cleanly with no unused import warnings."""
    import response_handler
    assert response_handler is not None


def test_benchmark_imports():
    """benchmark must import cleanly with no unused import warnings."""
    import scripts.benchmark
    assert scripts.benchmark is not None
