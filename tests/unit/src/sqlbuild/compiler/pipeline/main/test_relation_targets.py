from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models.core import CompiledObjectKey, CompiledProject, CompiledSource
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredSourceFile
from sqlbuild.compiler.pipeline.main.operations.relation_targets import (
    build_python_relation_targets,
)
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.refs import source
from sqlbuild.shared.models import SqlResourceRef
from sqlbuild.spec.models.source import SourceEntry
from tests.unit.src.sqlbuild.compiler.pipeline.main._test_types import (
    PythonRelationTargetsTestCase,
)
from tests.unit.src.sqlbuild.compiler.pipeline.main.helpers import RelationTargetTestAdapter


@pytest.mark.parametrize(
    "test_case",
    [
        PythonRelationTargetsTestCase(
            description="source refs use source read map instead of load map",
            expected_source_relation="deferred_raw.orders",
        )
    ],
    ids=["source refs use source read map instead of load map"],
)
def test_given_source_read_map_when_building_python_relation_targets_then_uses_read_relation(
    test_case: PythonRelationTargetsTestCase,
) -> None:
    raw_source: SourceEntry = SourceEntry(name="orders", schema="load_raw", table="orders")
    read_source: SourceEntry = SourceEntry(name="orders", schema="deferred_raw", table="orders")
    source_file: DiscoveredSourceFile = DiscoveredSourceFile(
        file_path=Path("sources/raw.yml"),
        relative_path=Path("sources/raw.yml"),
        contents="",
        source_entries=(raw_source,),
    )
    project: CompiledProject = CompiledProject(
        run_id="test_run",
        effective_target_name="dev",
        effective_connection={},
        effective_vars={},
        sources=(
            CompiledSource(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.SOURCE,
                    name="orders",
                ),
                deps=(),
                name="orders",
                source_entry=raw_source,
                source_file=source_file,
            ),
        ),
    )
    plan_output: PlanOutput = PlanOutput(
        source_map={"orders": raw_source},
        source_read_map={"orders": read_source},
    )

    targets: dict[SqlResourceRef, str] = build_python_relation_targets(
        adapter=RelationTargetTestAdapter(),
        project=project,
        plan_output=plan_output,
    )

    assert targets[source("orders")] == test_case.expected_source_relation
