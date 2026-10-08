"""Incremental edit compiles must match an uncached compile of the same edited project."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    BrokenChangeDetectionTestCase,
    ExternalModuleEditTestCase,
    IncrementalEditSequenceTestCase,
    RandomEditChainTestCase,
    RenderLoadNoticeTestCase,
    RenderSavePolicyTestCase,
    RenderStoreNoticeTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    CompileReuseRun,
    IncrementalEditComparison,
    RandomEditChain,
    add_external_flavor_macro,
    compare_incremental_compile,
    compile_in_process,
    compile_in_process_output,
    compiled_text,
    completed_order_udf_signature_change,
    disable_change_detection,
    edit_and_compile,
    enable_compile_reuse,
    fact_audit_added,
    fact_comment,
    fact_error_fixed,
    fact_error_introduced,
    full_edit_step,
    in_process_reuse_run,
    is_model_only_edit,
    json_report_keys,
    model_edit_step,
    move_project_file,
    order_status_nullability_change,
    payment_expression_type_change,
    prime_render_store,
    prime_render_store_in_process,
    random_edit_plan,
    render_store_files,
    replace_project_text,
    run_reuse_compile,
    set_render_load_notice_bytes,
    set_store_notice_renders,
    staging_comment,
    staging_contract_change,
    staging_header_change,
    staging_new_column,
    staging_type_change,
    star_chain_added,
    write_external_flavor,
    write_generated_edit_models,
    write_project_file,
)


@pytest.mark.parametrize(
    "test_case",
    [
        IncrementalEditSequenceTestCase(
            description="model_edits",
            steps=(
                model_edit_step("comment_without_shape_change", staging_comment),
                model_edit_step("type_change_propagates_downstream", staging_type_change),
                model_edit_step("new_output_column", staging_new_column),
                model_edit_step("header_config_change", staging_header_change),
                model_edit_step("column_contract_change", staging_contract_change),
                model_edit_step("attached_audit_added", fact_audit_added),
                model_edit_step("error_introduced", fact_error_introduced),
                model_edit_step("error_fixed", fact_error_fixed),
            ),
        ),
        IncrementalEditSequenceTestCase(
            description="model_set_changes",
            steps=(
                full_edit_step(
                    "model_added",
                    lambda root: write_project_file(
                        root,
                        "models/marts/order_quantities.sql",
                        "MODEL (description 'Order quantities.');\n\n"
                        'SELECT order_id, quantity FROM __ref("stg_orders")\n',
                    ),
                ),
                model_edit_step("edit_after_add", staging_comment),
                full_edit_step(
                    "model_renamed",
                    lambda root: move_project_file(
                        root,
                        "models/marts/order_quantities.sql",
                        "models/marts/order_quantity_totals.sql",
                    ),
                ),
                full_edit_step(
                    "model_removed",
                    lambda root: (root / "models/marts/order_quantity_totals.sql").unlink(),
                ),
                model_edit_step("edit_after_remove", fact_comment),
            ),
        ),
        IncrementalEditSequenceTestCase(
            description="declaration_edits",
            steps=(
                full_edit_step(
                    "macro_edit",
                    lambda root: replace_project_text(
                        root,
                        "macros/currency.py",
                        "{price_cents} * {quantity}",
                        "{quantity} * {price_cents}",
                    ),
                ),
                model_edit_step("edit_after_macro", fact_comment),
                full_edit_step(
                    "module_imported_by_macro_edit",
                    lambda root: replace_project_text(
                        root, "macros/_rounding.py", "_SCALE: int = 2", "_SCALE: int = 3"
                    ),
                ),
                full_edit_step(
                    "scoped_macro_edit",
                    lambda root: replace_project_text(
                        root,
                        "models/marts/_sqlbuild/_macros/currency.py",
                        "/ 100.0, 2)",
                        "/ 100.0, 3)",
                    ),
                ),
                full_edit_step(
                    "path_defaults_edit",
                    lambda root: replace_project_text(
                        root,
                        "sqlbuild_project.toml",
                        '[path_defaults.staging]\nmaterialized = "view"',
                        '[path_defaults.staging]\nmaterialized = "table"',
                    ),
                ),
                full_edit_step(
                    "enum_edit",
                    lambda root: replace_project_text(
                        root,
                        "models/marts/_sqlbuild/_enums/order_channel.sql",
                        'WEB "web"',
                        'WEB "online"',
                    ),
                ),
                full_edit_step(
                    "constant_edit",
                    lambda root: replace_project_text(
                        root,
                        "models/marts/_sqlbuild/_constants/min_quantity.sql",
                        "value 1)",
                        "value 2)",
                    ),
                ),
                full_edit_step(
                    "new_scope_folder",
                    lambda root: write_project_file(
                        root,
                        "models/staging/_sqlbuild/_macros/staging_totals.py",
                        "def staging_total_cents(price_cents: str, quantity: str) -> str:\n"
                        '    """Calculate a staging line total."""\n'
                        '    return f"({price_cents}) * ({quantity})"\n',
                    ),
                ),
                model_edit_step("edit_after_declarations", staging_comment),
            ),
        ),
        IncrementalEditSequenceTestCase(
            description="resource_edits",
            steps=(
                full_edit_step(
                    "seed_edit",
                    lambda root: replace_project_text(
                        root, "seeds/waffle_types.csv", "Classic Belgian", "Classic Brussels"
                    ),
                ),
                full_edit_step(
                    "source_edit",
                    lambda root: replace_project_text(
                        root,
                        "sources/raw.yml",
                        "      - name: quantity\n        type: INTEGER",
                        "      - name: quantity\n        type: BIGINT",
                    ),
                ),
                model_edit_step("edit_after_source", staging_type_change),
                full_edit_step(
                    "test_edit",
                    lambda root: replace_project_text(
                        root,
                        "tests/unit/test_stg_orders.sql",
                        "100 AS customer_id",
                        "101 AS customer_id",
                    ),
                ),
                full_edit_step(
                    "audit_edit",
                    lambda root: replace_project_text(
                        root,
                        "models/marts/_sqlbuild/_audits/generic/expression_is_true.sql",
                        "WHERE NOT (@expression)",
                        "WHERE NOT (@expression) AND 1 = 1",
                    ),
                ),
                model_edit_step("edit_after_resources", fact_comment),
            ),
        ),
        IncrementalEditSequenceTestCase(
            description="analysis_input_edits",
            steps=(
                full_edit_step("star_chain_added", star_chain_added),
                model_edit_step("upstream_type_flips_downstream_shapes", staging_type_change),
                model_edit_step("contract_type_edit", staging_contract_change),
                full_edit_step("source_expression_edit", payment_expression_type_change),
                full_edit_step("udf_signature_edit", completed_order_udf_signature_change),
                full_edit_step("schema_entry_nullability_edit", order_status_nullability_change),
                model_edit_step("edit_after_analysis_inputs", fact_comment),
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
    primed: CompileReuseRun = prime_render_store(project_dir)
    assert (cold.returncode, primed.returncode) == (0, 0), primed.stderr

    for step in test_case.steps:
        step.edit(project_dir)
        step.between(project_dir)
        comparison: IncrementalEditComparison = compare_incremental_compile(project_dir=project_dir)

        assert comparison.incremental.reused is False, step.description
        assert comparison.matches is test_case.expected_matches_uncached, (
            step.description,
            comparison.mismatched_artifacts,
            comparison.incremental.stderr,
        )
        assert (comparison.reused_renders > 0) is step.expected_render_reuse, step.description


@pytest.mark.parametrize(
    "test_case",
    [
        RandomEditChainTestCase(description="seed_7", seed=7, model_count=24, step_count=12),
        RandomEditChainTestCase(description="seed_19", seed=19, model_count=24, step_count=12),
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
    primed: CompileReuseRun = prime_render_store(project_dir)
    assert (cold.returncode, primed.returncode) == (0, 0), primed.stderr
    chain: RandomEditChain = RandomEditChain(project_dir=project_dir, seed=test_case.seed)

    for step, kind in enumerate(
        random_edit_plan(seed=test_case.seed, step_count=test_case.step_count)
    ):
        chain.apply(kind)
        chain.intervene()
        comparison: IncrementalEditComparison = compare_incremental_compile(project_dir=project_dir)

        assert comparison.matches is test_case.expected_matches_uncached, (
            step,
            kind,
            comparison.mismatched_artifacts,
            comparison.incremental.stderr,
        )
        assert (comparison.reused_renders > 0) is is_model_only_edit(kind), (step, kind)
        assert (comparison.incremental.timings.get("analysis_reuse_hits", 0) > 0) is (
            is_model_only_edit(kind)
        ), (step, kind)


@pytest.mark.parametrize(
    "test_case",
    [
        BrokenChangeDetectionTestCase(
            description="new_output_column",
            edit=staging_new_column,
            expected_matches_uncached=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_broken_change_detection_when_compiling_an_edit_then_the_oracle_reports_a_mismatch(
    compile_reuse_project: Path,
    test_case: BrokenChangeDetectionTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = compile_reuse_project
    enable_compile_reuse(monkeypatch)
    assert prime_render_store_in_process(project_dir) == 0
    test_case.edit(project_dir)
    disable_change_detection(monkeypatch)

    broken: CompileReuseRun = in_process_reuse_run(project_dir=project_dir, capsys=capsys)
    reference: CompileReuseRun = run_reuse_compile(project_dir=project_dir, args=("--no-cache",))
    comparison: IncrementalEditComparison = IncrementalEditComparison(
        incremental=broken, reference=reference
    )

    assert comparison.reused_renders > 0
    assert comparison.matches is test_case.expected_matches_uncached


@pytest.mark.parametrize(
    "test_case",
    [
        RenderStoreNoticeTestCase(
            description="few_renders_store_quietly", notice_renders=100_000, expected_notice=False
        ),
        RenderStoreNoticeTestCase(
            description="many_renders_announce_recording", notice_renders=1, expected_notice=True
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_new_renders_when_storing_after_an_edit_then_slow_recording_is_announced(
    compile_reuse_project: Path,
    test_case: RenderStoreNoticeTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    enable_compile_reuse(monkeypatch)
    set_store_notice_renders(monkeypatch, test_case.notice_renders)
    assert compile_in_process(project_dir=compile_reuse_project) == 0
    fact_comment(compile_reuse_project)

    code, _, err = compile_in_process_output(project_dir=compile_reuse_project, capsys=capsys)

    assert code == 0
    assert ("renders)..." in err) is test_case.expected_notice
    assert ("Recorded compile for reuse" in err) is test_case.expected_notice


@pytest.mark.parametrize(
    "test_case",
    [
        RenderSavePolicyTestCase(
            description="cold_then_two_model_edits",
            edits=(fact_comment, staging_comment),
            expected_cold_render_files=0,
            expected_render_files=(1, 2),
            expected_reused=(False, True),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cold_compile_when_editing_then_renders_are_stored_only_once_a_compile_exists(
    compile_reuse_project: Path, test_case: RenderSavePolicyTestCase
) -> None:
    cold: CompileReuseRun = run_reuse_compile(project_dir=compile_reuse_project)
    cold_render_files: int = render_store_files(compile_reuse_project)
    render_files: list[int] = []
    reused: list[bool] = []

    for edit in test_case.edits:
        run: CompileReuseRun = edit_and_compile(project_dir=compile_reuse_project, edit=edit)
        assert run.returncode == 0, run.stderr
        render_files.append(render_store_files(compile_reuse_project))
        reused.append(run.timings.get("render_reuse_hits", 0) > 0)

    assert cold.returncode == 0, cold.stderr
    assert cold_render_files == test_case.expected_cold_render_files
    assert tuple(render_files) == test_case.expected_render_files
    assert tuple(reused) == test_case.expected_reused


@pytest.mark.parametrize(
    "test_case",
    [
        ExternalModuleEditTestCase(
            description="module_rewritten_in_place_after_reuse",
            initial_value="'vanilla'",
            edited_value="'choco'",
            expected_matches_uncached=True,
            expected_compiled_value="'choco' AS flavor",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_module_imported_only_while_rendering_when_it_changes_after_reuse_then_output_is_fresh(
    compile_reuse_project: Path, tmp_path: Path, test_case: ExternalModuleEditTestCase
) -> None:
    extlib: Path = tmp_path / "extlib"
    env: dict[str, str] = add_external_flavor_macro(
        project_dir=compile_reuse_project, extlib=extlib, value=test_case.initial_value
    )
    cold: CompileReuseRun = run_reuse_compile(project_dir=compile_reuse_project, env=env)
    staging_comment(compile_reuse_project)
    recorded: CompileReuseRun = run_reuse_compile(project_dir=compile_reuse_project, env=env)
    staging_comment(compile_reuse_project)
    reused: CompileReuseRun = run_reuse_compile(project_dir=compile_reuse_project, env=env)

    write_external_flavor(extlib, test_case.edited_value)
    comparison: IncrementalEditComparison = IncrementalEditComparison(
        incremental=run_reuse_compile(project_dir=compile_reuse_project, env=env),
        reference=run_reuse_compile(
            project_dir=compile_reuse_project, env=env, args=("--no-cache",)
        ),
    )

    assert (cold.returncode, recorded.returncode, reused.returncode) == (0, 0, 0), reused.stderr
    assert reused.timings.get("render_reuse_hits", 0) > 0
    assert comparison.matches is test_case.expected_matches_uncached, (
        comparison.mismatched_artifacts
    )
    assert test_case.expected_compiled_value in compiled_text(
        run=comparison.incremental, suffix="fact_orders.sql"
    )


@pytest.mark.parametrize(
    "test_case",
    [
        RenderLoadNoticeTestCase(
            description="small_store_loads_quietly", notice_bytes=1 << 40, expected_notice=False
        ),
        RenderLoadNoticeTestCase(
            description="large_store_announces_loading", notice_bytes=1, expected_notice=True
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_stored_renders_when_loading_them_then_large_loads_are_announced_on_stderr(
    compile_reuse_project: Path,
    test_case: RenderLoadNoticeTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    enable_compile_reuse(monkeypatch)
    set_render_load_notice_bytes(monkeypatch, test_case.notice_bytes)
    assert prime_render_store_in_process(compile_reuse_project) == 0
    staging_comment(compile_reuse_project)

    code, out, err = compile_in_process_output(project_dir=compile_reuse_project, capsys=capsys)

    assert code == 0
    assert "compile_timings" in json_report_keys(out)
    assert ("Loading stored renders" in err) is test_case.expected_notice
    assert ("Loaded stored renders" in err) is test_case.expected_notice
