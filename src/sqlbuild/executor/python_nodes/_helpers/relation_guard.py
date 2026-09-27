"""Runtime relation guards for task, asset, and check contexts."""

from __future__ import annotations

from sqlbuild.compiler.references.types import HardCodedRelationOwnerKind
from sqlbuild.executor.python_nodes.classes.runtime_relation_guard import RuntimeRelationGuard
from sqlbuild.executor.python_nodes.models import PythonNodeRuntime


def build_python_node_relation_guard(
    *, owner_label: str, runtime: PythonNodeRuntime, warnings: list[str]
) -> RuntimeRelationGuard | None:
    """Return the hard-coded relation guard for one node, or None when enforcement is off."""

    if runtime.project_relations is None:
        return None
    return RuntimeRelationGuard(
        owner_label=owner_label,
        owner_kind=HardCodedRelationOwnerKind.NODE,
        project_relations=runtime.project_relations,
        dialect=runtime.adapter.sql_analysis_dialect(),
        default_database=runtime.default_database,
        default_schema=runtime.default_schema,
        warnings=warnings,
    )
