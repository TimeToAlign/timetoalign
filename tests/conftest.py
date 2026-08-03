"""Shared pytest fixtures for timetoalign tests."""

from __future__ import annotations

import contextlib

# Import ms3 in the controller process first: its packaging machinery may
# (re)write a generated version module on import, and concurrent first
# imports across xdist workers can race on that write.
with contextlib.suppress(Exception):
    import ms3  # noqa: F401

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--runslow",
        action="store_true",
        default=False,
        help="run tests marked slow (long-running corpus-scale integration tests)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runslow"):
        return
    skip_slow = pytest.mark.skip(reason="slow test: pass --runslow to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
