"""Suite-wide test configuration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sqlbuild._native import COMPILE_REUSE_DISABLE_ENV_VAR as REUSE_DISABLE_ENV_VAR

NATIVE_FIELD_STRICT_ENV_VAR: str = "SQLBUILD_NATIVE_FIELD_STRICT"
NATIVE_FIELD_ALLOWLIST: Path = Path(__file__).parent / "native_field_fallbacks.txt"


def pytest_configure(config: pytest.Config) -> None:
    """Exercise full compiles and fail on new native field fallbacks to Python by default."""

    del config
    os.environ.setdefault(REUSE_DISABLE_ENV_VAR, "1")
    os.environ.setdefault(NATIVE_FIELD_STRICT_ENV_VAR, f"enforce:{NATIVE_FIELD_ALLOWLIST}")
