"""Suite-wide test configuration."""

from __future__ import annotations

import os

import pytest

from sqlbuild.cli.compile_reuse.constants import REUSE_DISABLE_ENV_VAR, REUSE_DISABLE_VALUE
from sqlbuild.compiler.compile._helpers.native_stages import assembly as native_assembly


def pytest_configure(config: pytest.Config) -> None:
    """Exercise full compiles by default; compile reuse tests opt back in explicitly."""

    del config
    os.environ.setdefault(REUSE_DISABLE_ENV_VAR, REUSE_DISABLE_VALUE)


@pytest.fixture
def deferred_native_expression_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make native expression-source shapes defer, so compiles run the Python shape inference."""

    monkeypatch.setattr(native_assembly, "infer_native_expression_source_shapes", lambda **_: None)
