from __future__ import annotations

import pytest


def apply_no_progress_env(*, monkeypatch: pytest.MonkeyPatch, env_value: str | None) -> None:
    if env_value is None:
        monkeypatch.delenv("SQLBUILD_NO_PROGRESS", raising=False)
        return
    monkeypatch.setenv("SQLBUILD_NO_PROGRESS", env_value)
