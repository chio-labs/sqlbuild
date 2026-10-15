"""Suite-wide test configuration."""

from __future__ import annotations

import os

import pytest

from sqlbuild._native import COMPILE_REUSE_DISABLE_ENV_VAR as REUSE_DISABLE_ENV_VAR


def pytest_configure(config: pytest.Config) -> None:
    """Exercise full compiles by default; compile reuse tests opt back in explicitly."""

    del config
    os.environ.setdefault(REUSE_DISABLE_ENV_VAR, "1")
