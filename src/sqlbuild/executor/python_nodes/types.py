"""Type declarations for Python-node execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlbuild.compiler.discovery.models import DiscoveredAssetFunction, DiscoveredTaskFunction
from sqlbuild.compiler.python_nodes.models import PythonNodeIdentity

type ExecutablePythonNode = DiscoveredTaskFunction | DiscoveredAssetFunction

if TYPE_CHECKING:
    from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult


class PythonIdentityRecorder(Protocol):
    def __call__(
        self, *, identity: PythonNodeIdentity | None, _target_name: str | None
    ) -> None: ...


class OwnedResultCallback(Protocol):
    def __call__(
        self, *, node: ExecutablePythonNode, result: PythonNodeExecutionResult
    ) -> None: ...
