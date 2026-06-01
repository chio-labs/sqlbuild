"""Type declarations for Python-node execution."""

from __future__ import annotations

from sqlbuild.compiler.discovery.models import DiscoveredAssetFunction, DiscoveredTaskFunction

type ExecutablePythonNode = DiscoveredTaskFunction | DiscoveredAssetFunction
