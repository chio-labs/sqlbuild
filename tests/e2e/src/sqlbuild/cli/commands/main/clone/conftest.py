"""Fixtures for clone E2E tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.clone.helpers import prepare_origin_project


@pytest.fixture(scope="module")
def origin_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A project whose prod target is built, except `orders_backlog`, shared read-only."""

    return prepare_origin_project(tmp_path_factory.mktemp("clone_preparation_origin"))
