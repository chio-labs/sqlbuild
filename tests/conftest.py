"""Suite-wide test configuration."""

from __future__ import annotations

import os

import pytest

from sqlbuild.cli.compile_reuse.constants import REUSE_DISABLE_ENV_VAR, REUSE_DISABLE_VALUE


def pytest_configure(config: pytest.Config) -> None:
    """Exercise full compiles by default; compile reuse tests opt back in explicitly."""

    del config
    os.environ.setdefault(REUSE_DISABLE_ENV_VAR, REUSE_DISABLE_VALUE)
