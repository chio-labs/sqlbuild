from __future__ import annotations

import pytest

_NO_PROGRESS_ENV_VAR: str = "SQLBUILD_NO_PROGRESS"


def apply_no_progress_env(*, monkeypatch: pytest.MonkeyPatch, env_value: str | None) -> None:
    """Set or clear the SQLBUILD_NO_PROGRESS env var for a status test."""

    if env_value is None:
        monkeypatch.delenv(_NO_PROGRESS_ENV_VAR, raising=False)
        return
    monkeypatch.setenv(_NO_PROGRESS_ENV_VAR, env_value)
