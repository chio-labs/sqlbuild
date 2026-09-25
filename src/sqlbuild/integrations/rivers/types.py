"""Rivers integration shared types."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

type SqlBuildDagInput = Mapping[str, Any] | str | Path
type DagNode = Mapping[str, Any]
type DagCheck = Mapping[str, Any]
type DagEdge = Mapping[str, Any]
