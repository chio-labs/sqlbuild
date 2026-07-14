"""Shared fixtures for CLI entrypoint tests."""

from __future__ import annotations

import pytest

from sqlbuild.cli.commands._helpers.entry.constants import SQLBUILD_CONCURRENCY_ENV_VAR


@pytest.fixture(autouse=True)
def isolate_concurrency_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep entrypoint tests deterministic regardless of ambient SQLBUILD_CONCURRENCY.

    The CLI parser falls back to the SQLBUILD_CONCURRENCY environment variable for
    build/load/seed commands. The Makefile exports SQLBUILD_CONCURRENCY for pytest
    runs, so without this isolation the dispatch tests would observe the exported
    value instead of the parsed CLI default.
    """

    monkeypatch.delenv(SQLBUILD_CONCURRENCY_ENV_VAR, raising=False)
