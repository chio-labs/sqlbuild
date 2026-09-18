"""Test helpers for build execution command boundaries."""

from types import ModuleType
from unittest.mock import Mock

import pytest

from sqlbuild.cli.commands.models import BuildInvocation
from sqlbuild.spec.contracts.models import ExecutionLimitsConfig


def stub_resolved_build_invocation(
    *, monkeypatch: pytest.MonkeyPatch, build_module: ModuleType
) -> None:
    """Keep command-wrapper tests isolated from project discovery."""

    invocation: Mock = Mock(spec=BuildInvocation)
    invocation.execution_limits = ExecutionLimitsConfig()
    invocation.effective_target_name = None
    monkeypatch.setattr(build_module, "resolve_build_invocation", lambda **_kwargs: invocation)
