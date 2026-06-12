"""Type declarations for Python-node execution."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.compiler.discovery.models import DiscoveredAssetFunction, DiscoveredTaskFunction
from sqlbuild.compiler.python_nodes.models import PythonNodeIdentity

type ExecutablePythonNode = DiscoveredTaskFunction | DiscoveredAssetFunction
type PythonIdentityRecorder = Callable[[PythonNodeIdentity | None, str | None], None]
