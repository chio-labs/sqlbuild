"""Constants for the Rivers integration."""

from __future__ import annotations

from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.compiler.python_nodes.types import PythonNodeKind
from sqlbuild.runtime.contracts.types import ExecutionResourceKind

RIVERS_DEPLOYMENT_ENVIRONMENT_VARIABLE: str = "RIVERS_DEPLOYMENT"
RIVERS_DEVELOPMENT_DEPLOYMENT: str = "dev"
RIVERS_MODEL_KIND: str = CompiledResourceType.MODEL
RIVERS_VIEW_MATERIALIZATION: str = MaterializationType.VIEW
RIVERS_DIRECT_ASSET_KINDS: frozenset[str] = frozenset(
    {
        CompiledResourceType.SOURCE,
        ExecutionResourceKind.LOADER,
        CompiledResourceType.SEED,
        CompiledResourceType.UDF,
        CompiledResourceType.TABLE_FN,
        PythonNodeKind.TASK,
        PythonNodeKind.ASSET,
    }
)
