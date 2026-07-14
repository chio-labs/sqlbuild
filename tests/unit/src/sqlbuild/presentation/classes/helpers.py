from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType
from typing import cast

import pytest


def _delete_no_progress_env(monkeypatch: pytest.MonkeyPatch, env_value: str | None) -> None:
    del env_value
    monkeypatch.delenv("SQLBUILD_NO_PROGRESS", raising=False)


def _set_no_progress_env(monkeypatch: pytest.MonkeyPatch, env_value: str | None) -> None:
    monkeypatch.setenv("SQLBUILD_NO_PROGRESS", cast(str, env_value))


def apply_no_progress_env(*, monkeypatch: pytest.MonkeyPatch, env_value: str | None) -> None:
    _NO_PROGRESS_ENV_ACTIONS[env_value is None](monkeypatch, env_value)


_NO_PROGRESS_ENV_ACTIONS: MappingProxyType[
    bool, Callable[[pytest.MonkeyPatch, str | None], None]
] = MappingProxyType({True: _delete_no_progress_env, False: _set_no_progress_env})
