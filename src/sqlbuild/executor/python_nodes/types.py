"""Type declarations for Python-node execution."""

from __future__ import annotations

from typing import Protocol

from sqlbuild.compiler.discovery.models import DiscoveredAssetFunction, DiscoveredTaskFunction
from sqlbuild.compiler.python_nodes.models import PythonNodeIdentity

type ExecutablePythonNode = DiscoveredTaskFunction | DiscoveredAssetFunction


class PythonIdentityRecorder(Protocol):
    def __call__(
        self, identity: PythonNodeIdentity | None, *, _target_name: str | None
    ) -> None: ...
