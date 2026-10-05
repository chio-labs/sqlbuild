"""Incremental edit compiles must match an uncached compile of the same edited project."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

import sqlbuild.cli.compile_reuse._helpers.attempt as reuse_attempt
from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    IncrementalEditSequenceTestCase,
    IncrementalEditStep,
    RandomEditChainTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    CompileReuseRun,
    IncrementalEditComparison,
    RandomEditChain,
    compare_incremental_compile,
    compile_in_process,
    enable_compile_reuse,
    in_process_reuse_run,
    move_project_file,
    replace_project_text,
    run_reuse_compile,
    write_generated_edit_models,
    write_project_file,
)

_STG_ORDERS: str = "models/staging/stg_orders.sql"
_FACT_ORDERS: str = "models/marts/fact_orders.sql"


def _model_comment(root: Path) -> None:
    replace_project_text(
        root, _STG_ORDERS, 'FROM __source("raw__orders")', '-- staged\nFROM __source("raw__orders")'
    )


def _model_type_change(root: Path) -> None:
    replace_project_text(
        root, _STG_ORDERS, "  quantity,\n", "  CAST(quantity AS BIGINT) AS quantity,\n"
    )


def _model_new_column(root: Path) -> None:
    replace_project_text(root, _STG_ORDERS, "  status\n", "  status,\n  status AS raw_status\n")


def _model_header_change(root: Path) -> None:
    replace_project_text(root, _STG_ORDERS, "materialized view,", "materialized table,")


def _model_contract_change(root: Path) -> None:
    replace_project_text(
        root,
        _STG_ORDERS,
        "customer_id (nullable false, audits [not_null]),",
        "customer_id (type BIGINT, nullable false, audits [not_null]),",
    )


def _introduce_error(root: Path) -> None:
    replace_project_text(root, _FACT_ORDERS, "  o.quantity,\n", "  o.missing_quantity,\n")


def _fix_error(root: Path) -> None:
    replace_project_text(root, _FACT_ORDERS, "  o.missing_quantity,\n", "  o.quantity,\n")


def _leaf_comment(root: Path) -> None:
    replace_project_text(root, _FACT_ORDERS, "FROM __ref", "-- leaf\nFROM __ref")


def _model_step(description: str, edit: Callable[[Path], None]) -> IncrementalEditStep:
    return IncrementalEditStep(description=description, edit=edit, reuses_renders=True)


def _full_step(description: str, edit: Callable[[Path], None]) -> IncrementalEditStep:
    return IncrementalEditStep(description=description, edit=edit, reuses_renders=False)


@pytest.mark.parametrize(
    "test_case",
    [
        IncrementalEditSequenceTestCase(
            description="model_edits",
            steps=(
                _model_step("comment_without_shape_change", _model_comment),
                _model_step("type_change_propagates_downstream", _model_type_change),
                _model_step("new_output_column", _model_new_column),
                _model_step("header_config_change", _model_header_change),
                _model_step("column_contract_change", _model_contract_change),
                _model_step("error_introduced", _introduce_error),
                _model_step("error_fixed", _fix_error),
            ),
        ),
        IncrementalEditSequenceTestCase(
            description="model_set_changes",
            steps=(
                _full_step(
                    "model_added",
                    lambda root: write_project_file(
                        root,
                        "models/marts/order_quantities.sql",
                        "MODEL (description 'Order quantities.');\n\n"
                        'SELECT order_id, quantity FROM __ref("stg_orders")\n',
                    ),
                ),
                _model_step("edit_after_add", _model_comment),
                _full_step(
                    "model_renamed",
                    lambda root: move_project_file(
                        root,
                        "models/marts/order_quantities.sql",
                        "models/marts/order_quantity_totals.sql",
                    ),
                ),
                _full_step(
                    "model_removed",
                    lambda root: (root / "models/marts/order_quantity_totals.sql").unlink(),
                ),
                _model_step("edit_after_remove", _leaf_comment),
            ),
        ),
        IncrementalEditSequenceTestCase(
            description="declaration_edits",
            steps=(
                _full_step(
                    "macro_edit",
                    lambda root: replace_project_text(
                        root,
                        "macros/currency.py",
                        "{price_cents} * {quantity}",
                        "{quantity} * {price_cents}",
                    ),
                ),
                _model_step("edit_after_macro", _leaf_comment),
                _full_step(
                    "module_imported_by_macro_edit",
                    lambda root: replace_project_text(
                        root, "macros/_rounding.py", "_SCALE: int = 2", "_SCALE: int = 3"
                    ),
                ),
                _full_step(
                    "scoped_macro_edit",
                    lambda root: replace_project_text(
                        root,
                        "models/marts/_sqlbuild/_macros/currency.py",
                        "/ 100.0, 2)",
                        "/ 100.0, 3)",
                    ),
                ),
                _full_step(
                    "path_defaults_edit",
                    lambda root: replace_project_text(
                        root,
                        "sqlbuild_project.toml",
                        '[path_defaults.staging]\nmaterialized = "view"',
                        '[path_defaults.staging]\nmaterialized = "table"',
                    ),
                ),
                _full_step(
                    "enum_edit",
                    lambda root: replace_project_text(
                        root,
                        "models/marts/_sqlbuild/_enums/order_channel.sql",
                        'WEB "web"',
                        'WEB "online"',
                    ),
                ),
                _full_step(
                    "constant_edit",
                    lambda root: replace_project_text(
                        root,
                        "models/marts/_sqlbuild/_constants/min_quantity.sql",
                        "value 1)",
                        "value 2)",
                    ),
                ),
                _full_step(
                    "new_scope_folder",
                    lambda root: write_project_file(
                        root,
                        "models/staging/_sqlbuild/_macros/staging_totals.py",
                        "def staging_total_cents(price_cents: str, quantity: str) -> str:\n"
                        '    """Calculate a staging line total."""\n'
                        '    return f"({price_cents}) * ({quantity})"\n',
                    ),
                ),
                _model_step("edit_after_declarations", _model_comment),
            ),
        ),
        IncrementalEditSequenceTestCase(
            description="resource_edits",
            steps=(
                _full_step(
                    "seed_edit",
                    lambda root: replace_project_text(
                        root, "seeds/waffle_types.csv", "Classic Belgian", "Classic Brussels"
                    ),
                ),
                _full_step(
                    "source_edit",
                    lambda root: replace_project_text(
                        root,
                        "sources/raw.yml",
                        "      - name: quantity\n        type: INTEGER",
                        "      - name: quantity\n        type: BIGINT",
                    ),
                ),
                _model_step("edit_after_source", _model_type_change),
                _full_step(
                    "test_edit",
                    lambda root: replace_project_text(
                        root,
                        "tests/unit/test_stg_orders.sql",
                        "100 AS customer_id",
                        "101 AS customer_id",
                    ),
                ),
                _full_step(
                    "audit_edit",
                    lambda root: replace_project_text(
                        root,
                        "models/marts/_sqlbuild/_audits/generic/expression_is_true.sql",
                        "WHERE NOT (@expression)",
                        "WHERE NOT (@expression) AND 1 = 1",
                    ),
                ),
                _model_step("edit_after_resources", _leaf_comment),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_edit_sequence_when_compiling_incrementally_then_each_step_matches_uncached_compile(
    compile_reuse_project: Path, test_case: IncrementalEditSequenceTestCase
) -> None:
    project_dir: Path = compile_reuse_project
    cold: CompileReuseRun = run_reuse_compile(project_dir=project_dir)
    assert cold.returncode == 0, cold.stderr

    for step in test_case.steps:
        step.edit(project_dir)
        comparison: IncrementalEditComparison = compare_incremental_compile(project_dir=project_dir)

        assert comparison.incremental.reused is False, step.description
        assert comparison.mismatch() is None, (step.description, comparison.incremental.stderr)
        assert (comparison.reused_renders > 0) is step.reuses_renders, step.description


@pytest.mark.parametrize(
    "test_case",
    [
        RandomEditChainTestCase(description="seed_7", seed=7, model_count=24, step_count=14),
        RandomEditChainTestCase(description="seed_19", seed=19, model_count=24, step_count=14),
    ],
    ids=lambda case: case.description,
)
def test_given_random_edit_chain_when_compiling_incrementally_then_each_step_matches_uncached_compile(
    compile_reuse_project: Path, test_case: RandomEditChainTestCase
) -> None:
    project_dir: Path = compile_reuse_project
    write_generated_edit_models(
        project_dir=project_dir, model_count=test_case.model_count, seed=test_case.seed
    )
    cold: CompileReuseRun = run_reuse_compile(project_dir=project_dir)
    assert cold.returncode == 0, cold.stderr
    chain: RandomEditChain = RandomEditChain(project_dir=project_dir, seed=test_case.seed)

    for step in range(test_case.step_count):
        kind, model_only = chain.apply()
        comparison: IncrementalEditComparison = compare_incremental_compile(project_dir=project_dir)

        assert comparison.mismatch() is None, (step, kind, comparison.incremental.stderr)
        assert (comparison.reused_renders > 0) is model_only, (step, kind)


def test_given_broken_change_detection_when_compiling_an_edit_then_the_oracle_reports_a_mismatch(
    compile_reuse_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = compile_reuse_project
    enable_compile_reuse(monkeypatch)
    assert compile_in_process(project_dir=project_dir) == 0
    _model_new_column(project_dir)
    monkeypatch.setattr(reuse_attempt, "changed_project_paths", lambda **_kwargs: frozenset())

    broken: CompileReuseRun = in_process_reuse_run(project_dir=project_dir, capsys=capsys)
    reference: CompileReuseRun = run_reuse_compile(project_dir=project_dir, args=("--no-cache",))

    assert broken.timings["render_reuse_hits"] > 0
    assert IncrementalEditComparison(incremental=broken, reference=reference).mismatch() is not None
