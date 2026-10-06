"""Edits that reuse stored declarations, analyses, and artifacts must match an uncached compile."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    BrokenEditInvalidationTestCase,
    IncrementalEditSequenceTestCase,
    SharedCacheKeyTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    CompileReuseRun,
    IncrementalEditComparison,
    analyze_in_one_batch,
    analyze_one_model_at_a_time,
    build_between,
    compare_incremental_compile,
    compile_edit_without_reuse,
    compile_in_process,
    compile_without_reuse_between,
    compiled_artifact_tampered,
    enable_compile_reuse,
    fact_comment,
    fact_quantity_type_declared,
    fact_quantity_type_removed,
    full_edit_step,
    in_process_reuse_run,
    keep_invalidation,
    leave_edit_uncompiled,
    model_edit_step,
    other_target_build_between,
    payments_comment,
    plan_between,
    prime_render_store,
    prime_render_store_in_process,
    replace_project_text,
    reuse_declarations_after_any_edit,
    run_reuse_compile,
    skip_upstream_analysis_checks,
    staging_column_removed,
    staging_column_renamed,
    staging_column_restored,
    staging_comment,
    staging_extra_flag,
    staging_extra_flag_removed,
    staging_quantity_restored,
    staging_quantity_text,
    staging_rename_reverted,
    star_chain_added,
    star_chain_with_twin_added,
    stg_orders_test_edit,
    trust_changed_artifacts,
    twin_header_changed,
)


@pytest.mark.parametrize(
    "test_case",
    [
        IncrementalEditSequenceTestCase(
            description="upstream_shape_changes",
            steps=(
                model_edit_step("upstream_column_removed", staging_column_removed),
                model_edit_step("edit_while_downstream_broken", payments_comment),
                model_edit_step("upstream_column_restored", staging_column_restored),
                model_edit_step("upstream_column_renamed", staging_column_renamed),
                model_edit_step("upstream_rename_reverted", staging_rename_reverted),
            ),
        ),
        IncrementalEditSequenceTestCase(
            description="contract_changes",
            steps=(
                model_edit_step("downstream_type_declared", fact_quantity_type_declared),
                model_edit_step("upstream_type_breaks_contract", staging_quantity_text),
                model_edit_step("edit_after_contract_error", fact_comment),
                model_edit_step("upstream_type_restored", staging_quantity_restored),
                model_edit_step("downstream_type_removed", fact_quantity_type_removed),
            ),
        ),
        IncrementalEditSequenceTestCase(
            description="star_chain_after_plan",
            steps=(
                full_edit_step("star_chain_added", star_chain_added),
                model_edit_step("upstream_column_added", staging_extra_flag, plan_between),
                model_edit_step("edit_after_added_column", fact_comment),
                model_edit_step(
                    "upstream_column_removed", staging_extra_flag_removed, plan_between
                ),
                model_edit_step("edit_after_removed_column", payments_comment),
            ),
        ),
        IncrementalEditSequenceTestCase(
            description="star_chain_after_build",
            steps=(
                full_edit_step("star_chain_added", star_chain_added),
                model_edit_step("upstream_column_added", staging_extra_flag, build_between),
                model_edit_step("edit_after_added_column", fact_comment),
                model_edit_step(
                    "upstream_column_removed", staging_extra_flag_removed, build_between
                ),
                model_edit_step("edit_after_removed_column", payments_comment),
            ),
        ),
        IncrementalEditSequenceTestCase(
            description="star_chain_after_uncached_compile",
            steps=(
                full_edit_step("star_chain_added", star_chain_added),
                model_edit_step(
                    "upstream_column_added", staging_extra_flag, compile_without_reuse_between
                ),
                model_edit_step("edit_after_added_column", fact_comment),
                model_edit_step(
                    "upstream_column_removed",
                    staging_extra_flag_removed,
                    compile_without_reuse_between,
                ),
                model_edit_step("edit_after_removed_column", payments_comment),
            ),
        ),
        IncrementalEditSequenceTestCase(
            description="star_chain_after_other_target_build",
            steps=(
                full_edit_step("star_chain_added", star_chain_added),
                model_edit_step(
                    "upstream_column_added", staging_extra_flag, other_target_build_between
                ),
                model_edit_step("edit_after_added_column", fact_comment),
                model_edit_step(
                    "upstream_column_removed",
                    staging_extra_flag_removed,
                    other_target_build_between,
                ),
                model_edit_step("edit_after_removed_column", payments_comment),
            ),
        ),
        IncrementalEditSequenceTestCase(
            description="declarations_and_artifacts",
            steps=(
                full_edit_step(
                    "source_type_edit",
                    lambda root: replace_project_text(
                        root,
                        "sources/raw.yml",
                        "      - name: quantity\n        type: INTEGER",
                        "      - name: quantity\n        type: BIGINT",
                    ),
                ),
                model_edit_step("edit_after_source", staging_comment),
                model_edit_step("compiled_artifact_tampered", compiled_artifact_tampered),
                full_edit_step("test_edit", stg_orders_test_edit),
                model_edit_step("edit_after_test", fact_comment),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_edit_sequence_when_reusing_stored_phases_then_each_step_matches_uncached_compile(
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

        assert comparison.matches is test_case.expected_matches_uncached, (
            step.description,
            comparison.mismatched_artifacts,
            comparison.incremental.stderr,
        )
        assert (comparison.reused_renders > 0) is step.expected_render_reuse, step.description
        assert (
            comparison.incremental.timings.get("analysis_reuse_hits", 0) > 0
        ) is step.expected_render_reuse, step.description


@pytest.mark.parametrize(
    "test_case",
    [
        BrokenEditInvalidationTestCase(
            description="intact_invalidation_after_upstream_shape_change",
            compiled_edits=(),
            edit=staging_column_removed,
            sabotage=keep_invalidation,
            expected_matches_uncached=True,
            after_edit=compile_edit_without_reuse,
        ),
        BrokenEditInvalidationTestCase(
            description="analysis_served_despite_upstream_shape_change",
            compiled_edits=(),
            edit=staging_column_removed,
            sabotage=skip_upstream_analysis_checks,
            expected_matches_uncached=False,
            after_edit=compile_edit_without_reuse,
        ),
        BrokenEditInvalidationTestCase(
            description="intact_invalidation_after_test_edit",
            compiled_edits=(),
            edit=stg_orders_test_edit,
            sabotage=keep_invalidation,
            expected_matches_uncached=True,
            after_edit=leave_edit_uncompiled,
        ),
        BrokenEditInvalidationTestCase(
            description="declarations_reused_despite_test_edit",
            compiled_edits=(),
            edit=stg_orders_test_edit,
            sabotage=reuse_declarations_after_any_edit,
            expected_matches_uncached=False,
            after_edit=leave_edit_uncompiled,
        ),
        BrokenEditInvalidationTestCase(
            description="intact_invalidation_after_tampering",
            compiled_edits=(),
            edit=compiled_artifact_tampered,
            sabotage=keep_invalidation,
            expected_matches_uncached=True,
            after_edit=leave_edit_uncompiled,
        ),
        BrokenEditInvalidationTestCase(
            description="artifact_trusted_despite_tampering",
            compiled_edits=(),
            edit=compiled_artifact_tampered,
            sabotage=trust_changed_artifacts,
            expected_matches_uncached=False,
            after_edit=leave_edit_uncompiled,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_broken_edit_invalidation_when_compiling_an_edit_then_the_oracle_reports_a_mismatch(
    compile_reuse_project: Path,
    test_case: BrokenEditInvalidationTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = compile_reuse_project
    enable_compile_reuse(monkeypatch)
    assert prime_render_store_in_process(project_dir) == 0
    for edit in test_case.compiled_edits:
        edit(project_dir)
        assert compile_in_process(project_dir=project_dir) == 0
    test_case.edit(project_dir)
    test_case.after_edit(project_dir, monkeypatch)
    test_case.sabotage(monkeypatch)

    broken: CompileReuseRun = in_process_reuse_run(project_dir=project_dir, capsys=capsys)
    reference: CompileReuseRun = run_reuse_compile(project_dir=project_dir, args=("--no-cache",))
    comparison: IncrementalEditComparison = IncrementalEditComparison(
        incremental=broken, reference=reference
    )

    assert comparison.matches is test_case.expected_matches_uncached, (
        comparison.mismatched_artifacts
    )


@pytest.mark.parametrize(
    "test_case",
    [
        SharedCacheKeyTestCase(
            description="dataflow_one_model_at_a_time", schedule=analyze_one_model_at_a_time
        ),
        SharedCacheKeyTestCase(description="one_batch", schedule=analyze_in_one_batch),
    ],
    ids=lambda case: case.description,
)
def test_given_model_sharing_a_served_cache_key_when_upstream_changes_then_it_matches_uncached(
    compile_reuse_project: Path,
    test_case: SharedCacheKeyTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = compile_reuse_project
    enable_compile_reuse(monkeypatch)
    test_case.schedule(monkeypatch)
    star_chain_with_twin_added(project_dir)
    assert prime_render_store_in_process(project_dir) == 0
    staging_extra_flag(project_dir)
    twin_header_changed(project_dir)
    compile_edit_without_reuse(project_dir, monkeypatch)

    incremental: CompileReuseRun = in_process_reuse_run(project_dir=project_dir, capsys=capsys)
    reference: CompileReuseRun = in_process_reuse_run(
        project_dir=project_dir, capsys=capsys, args=("--no-cache",)
    )
    comparison: IncrementalEditComparison = IncrementalEditComparison(
        incremental=incremental, reference=reference
    )

    assert comparison.matches is test_case.expected_matches_uncached, (
        comparison.mismatched_artifacts
    )
    assert incremental.timings.get("analysis_reuse_hits", 0) > 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
