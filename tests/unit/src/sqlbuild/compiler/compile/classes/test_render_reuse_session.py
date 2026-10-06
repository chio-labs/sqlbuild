"""Render reuse must replay what an unchanged render reported and never serve a changed one."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile._helpers.diagnostics.collector import collect_compile_diagnostics
from sqlbuild.compiler.compile.classes.render_reuse_session import CompileRenderReuseSession
from sqlbuild.compiler.compile.constants import COMPILE_INPUT_READS
from sqlbuild.compiler.compile.models import CompileModelInput
from sqlbuild.compiler.discovery.models import DiscoveredDeclarationFiles, DiscoveredSqlModelFile
from tests.unit.src.sqlbuild.compiler.compile.classes._test_types import (
    CorruptRenderTestCase,
    DeclarationReuseTestCase,
    ReleasedRenderTestCase,
    RenderReplayTestCase,
    ReusableModelsTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile.classes.helpers import (
    DECLARATIONS_VARIANT,
    OTHER_DECLARATIONS_VARIANT,
    REGION_ENV_VAR,
    CountingDiscovery,
    corrupted_session,
    declaration_files,
    declarations_state,
    edited_session,
    missing_description,
    model_file,
    planned_session,
    released_paths,
    stored_query_sqls,
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


@pytest.mark.parametrize(
    "test_case",
    [
        ReleasedRenderTestCase(
            description="reused_from_base",
            retained_models=frozenset(),
            expected_released={"models/orders.sql": True, "models/customers.sql": False},
            expected_query_sqls={
                "models/orders.sql": "SELECT 1 AS order_id",
                "models/customers.sql": "SELECT 2 AS customer_id",
            },
        ),
        ReleasedRenderTestCase(
            description="reused_from_overlay",
            retained_models=frozenset({"models/orders.sql"}),
            expected_released={"models/orders.sql": False, "models/customers.sql": False},
            expected_query_sqls={
                "models/orders.sql": "SELECT 1 AS order_id",
                "models/customers.sql": "SELECT 2 AS customer_id",
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_reused_render_when_storing_then_base_bytes_are_released_and_recoverable(
    test_case: ReleasedRenderTestCase,
) -> None:
    session: CompileRenderReuseSession = edited_session(retained_models=test_case.retained_models)

    released: dict[str, bool] = released_paths(session.stored_state())
    complete: dict[str, str] = stored_query_sqls(session.stored_state(complete=True))

    assert released == test_case.expected_released
    assert complete == test_case.expected_query_sqls


@pytest.mark.parametrize(
    "test_case",
    [
        DeclarationReuseTestCase(
            description="model_edited",
            changed_paths=frozenset({"models/customers.sql"}),
            recorded_variant=DECLARATIONS_VARIANT,
            expected_full_discoveries=0,
        ),
        DeclarationReuseTestCase(
            description="model_added",
            changed_paths=frozenset({"models/returns.sql"}),
            recorded_variant=DECLARATIONS_VARIANT,
            expected_full_discoveries=1,
        ),
        DeclarationReuseTestCase(
            description="macro_edited",
            changed_paths=frozenset({"macros/currency.py"}),
            recorded_variant=DECLARATIONS_VARIANT,
            expected_full_discoveries=1,
        ),
        DeclarationReuseTestCase(
            description="changes_unknown",
            changed_paths=None,
            recorded_variant=DECLARATIONS_VARIANT,
            expected_full_discoveries=1,
        ),
        DeclarationReuseTestCase(
            description="declarations_stored_for_other_discovery",
            changed_paths=frozenset({"models/customers.sql"}),
            recorded_variant=OTHER_DECLARATIONS_VARIANT,
            expected_full_discoveries=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_stored_declarations_when_discovering_then_only_model_only_edits_reuse_them(
    test_case: DeclarationReuseTestCase,
) -> None:
    current: tuple[DiscoveredSqlModelFile, ...] = (
        model_file("orders"),
        model_file("customers", "SELECT 2 AS customer_id"),
    )
    discovery: CountingDiscovery = CountingDiscovery(current)
    session: CompileRenderReuseSession = CompileRenderReuseSession(
        prior=declarations_state(recorded_variant=test_case.recorded_variant),
        changed_paths=test_case.changed_paths,
    )

    with collect_compile_diagnostics():
        discovered: DiscoveredDeclarationFiles = session.declaration_files(
            variant=DECLARATIONS_VARIANT,
            discover=discovery.discover,
            discover_models=discovery.discover_models,
        )

    assert discovered == declaration_files(current)
    assert discovery.full == test_case.expected_full_discoveries


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
