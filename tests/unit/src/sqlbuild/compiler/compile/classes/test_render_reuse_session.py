"""Render reuse must replay what an unchanged render reported and never serve a changed one."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile._helpers.diagnostics.collector import collect_compile_diagnostics
from sqlbuild.compiler.compile.classes.render_reuse_session import CompileRenderReuseSession
from sqlbuild.compiler.compile.constants import COMPILE_INPUT_READS
from sqlbuild.compiler.compile.models import CompileModelInput
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile
from tests.unit.src.sqlbuild.compiler.compile.classes._test_types import (
    CorruptRenderTestCase,
    RenderReplayTestCase,
    ReusableModelsTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile.classes.helpers import (
    REGION_ENV_VAR,
    corrupted_session,
    missing_description,
    model_file,
    planned_session,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RenderReplayTestCase(
            description="unchanged_model",
            model_name="orders",
            expected_diagnostics=(missing_description("orders"),),
            expected_environment_names=(REGION_ENV_VAR,),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unchanged_model_when_reusing_then_render_and_reports_are_replayed(
    test_case: RenderReplayTestCase,
) -> None:
    unchanged: DiscoveredSqlModelFile = model_file(test_case.model_name)
    edited: DiscoveredSqlModelFile = model_file("customers", "SELECT 2 AS customer_id")
    session: CompileRenderReuseSession = planned_session(
        stored=(unchanged, model_file("customers")),
        current=(unchanged, edited),
        changed_paths=frozenset({str(edited.relative_path)}),
    )

    with (
        COMPILE_INPUT_READS.recording() as reads,
        collect_compile_diagnostics() as collected,
    ):
        reused: CompileModelInput | None = session.reused_model(model_file=unchanged)

    assert reused == CompileModelInput(model_file=unchanged, query_sql=unchanged.query_sql)
    assert reused is not None
    assert reused.model_file is unchanged
    assert collected.diagnostics == test_case.expected_diagnostics
    assert reads.environment_names == test_case.expected_environment_names


@pytest.mark.parametrize(
    "test_case",
    [
        ReusableModelsTestCase(
            description="changed_model",
            stored_models=("orders", "customers"),
            current_models=("orders", "customers"),
            changed_paths=frozenset({"models/customers.sql"}),
            run_id_readers=frozenset(),
            expected_reusable={"orders": True, "customers": False},
        ),
        ReusableModelsTestCase(
            description="render_read_run_identity",
            stored_models=("orders", "customers"),
            current_models=("orders", "customers"),
            changed_paths=frozenset(),
            run_id_readers=frozenset({"orders"}),
            expected_reusable={"orders": False, "customers": True},
        ),
        ReusableModelsTestCase(
            description="model_added",
            stored_models=("orders",),
            current_models=("orders", "customers"),
            changed_paths=frozenset({"models/customers.sql"}),
            run_id_readers=frozenset(),
            expected_reusable={"orders": False, "customers": False},
        ),
        ReusableModelsTestCase(
            description="model_removed",
            stored_models=("orders", "customers", "returns"),
            current_models=("orders", "customers"),
            changed_paths=frozenset(),
            run_id_readers=frozenset(),
            expected_reusable={"orders": False, "customers": False},
        ),
        ReusableModelsTestCase(
            description="non_model_input_changed",
            stored_models=("orders", "customers"),
            current_models=("orders", "customers"),
            changed_paths=frozenset({"macros/currency.py"}),
            run_id_readers=frozenset(),
            expected_reusable={"orders": False, "customers": False},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_stored_renders_when_planning_then_only_unchanged_identical_model_sets_reuse(
    test_case: ReusableModelsTestCase,
) -> None:
    current: tuple[DiscoveredSqlModelFile, ...] = tuple(map(model_file, test_case.current_models))
    session: CompileRenderReuseSession = planned_session(
        stored=tuple(map(model_file, test_case.stored_models)),
        current=current,
        changed_paths=test_case.changed_paths,
        run_id_readers=test_case.run_id_readers,
    )

    reusable: dict[str, bool] = {
        item.file_path.stem: session.has_reusable_model(model_file=item) for item in current
    }

    assert reusable == test_case.expected_reusable


@pytest.mark.parametrize(
    "test_case",
    [
        CorruptRenderTestCase(
            description="undecodable_payload", model_name="orders", expected_rendered_again=True
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_corrupt_stored_render_when_reusing_then_the_model_is_rendered_again(
    test_case: CorruptRenderTestCase,
) -> None:
    item: DiscoveredSqlModelFile = model_file(test_case.model_name)
    session: CompileRenderReuseSession = corrupted_session(item)

    with collect_compile_diagnostics():
        reused: CompileModelInput | None = session.reused_model(model_file=item)

    assert (reused is None) is test_case.expected_rendered_again


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
