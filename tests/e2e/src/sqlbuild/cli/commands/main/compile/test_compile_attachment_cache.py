"""Reused model attachment must match a cache-disabled compile through the real CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    AttachmentCacheReuseTestCase,
    AttachmentDiagnosticReplayTestCase,
    AttachmentReferencePolicyTestCase,
    AttachmentRunIdTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    COMPILE_CACHE_REGION_ENV_VAR,
    COMPILE_CACHE_SCHEMA_ENV_VAR,
    CompileCacheOutcome,
    attachment_cache_counts,
    compile_cache_outcome,
    compile_json_payload,
    compile_manifest_run_ids,
    outcome_attachment_counts,
    replace_project_text,
    write_project_file,
    write_project_files,
)


@pytest.mark.parametrize(
    "test_case",
    [
        AttachmentCacheReuseTestCase(
            description="model_added_attaches_only_the_new_model",
            edit=lambda root: write_project_file(
                root,
                "models/marts/order_quantities.sql",
                'MODEL (description "Order quantities");\n\n'
                'SELECT order_id, quantity FROM __ref("stg_orders")\n',
            ),
            expected_attachment_counts=(13, 1, 1),
        ),
        AttachmentCacheReuseTestCase(
            description="unreferenced_model_removed_reuses_the_rest",
            edit=lambda root: (root / "models/marts/dim_customers.sql").unlink(),
            expected_attachment_counts=(12, 0, 1),
        ),
        AttachmentCacheReuseTestCase(
            description="referenced_model_removed_fails_after_reuse",
            edit=lambda root: (root / "models/staging/stg_orders.sql").unlink(),
            expected_attachment_counts=(0, 0, 0),
            expected_failure=True,
        ),
        AttachmentCacheReuseTestCase(
            description="project_macro_edit_reattaches_every_model",
            edit=lambda root: replace_project_text(
                root,
                "macros/currency.py",
                'return f"{price_cents} * {quantity}"',
                'return f"({price_cents}) * ({quantity})"',
            ),
            expected_attachment_counts=(0, 14, 0),
        ),
        AttachmentCacheReuseTestCase(
            description="target_schema_environment_value_unchanged",
            setup=lambda root: replace_project_text(
                root,
                "sqlbuild_project.toml",
                'schema = "dev"',
                f'schema = "${{ENV:{COMPILE_CACHE_SCHEMA_ENV_VAR}}}"',
            ),
            edit=lambda root: None,
            initial_env={COMPILE_CACHE_SCHEMA_ENV_VAR: "analytics_east"},
            expected_attachment_counts=(13, 0, 1),
        ),
        AttachmentCacheReuseTestCase(
            description="target_schema_environment_value_changed",
            setup=lambda root: replace_project_text(
                root,
                "sqlbuild_project.toml",
                'schema = "dev"',
                f'schema = "${{ENV:{COMPILE_CACHE_SCHEMA_ENV_VAR}}}"',
            ),
            edit=lambda root: None,
            initial_env={COMPILE_CACHE_SCHEMA_ENV_VAR: "analytics_east"},
            edited_env={COMPILE_CACHE_SCHEMA_ENV_VAR: "analytics_west"},
            expected_attachment_counts=(0, 14, 0),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_warm_attachment_cache_when_project_changes_then_matches_uncached_reference(
    cache_invalidation_project: Path, test_case: AttachmentCacheReuseTestCase
) -> None:
    project_dir: Path = cache_invalidation_project
    test_case.setup(project_dir)
    initial_env: dict[str, str] = {COMPILE_CACHE_REGION_ENV_VAR: "east", **test_case.initial_env}
    cold: CompileCacheOutcome = compile_cache_outcome(project_dir=project_dir, env=initial_env)

    test_case.edit(project_dir)
    edited_env: dict[str, str] = {**initial_env, **test_case.edited_env}
    edited: CompileCacheOutcome = compile_cache_outcome(project_dir=project_dir, env=edited_env)
    reference: CompileCacheOutcome = compile_cache_outcome(
        project_dir=project_dir, env=edited_env, compile_args=("--no-cache",)
    )

    assert cold.returncode == 0
    assert outcome_attachment_counts(cold) == (0, 14, 0)
    assert edited[:3] == reference[:3]
    assert (edited.returncode != 0) is test_case.expected_failure
    assert outcome_attachment_counts(edited) == test_case.expected_attachment_counts


@pytest.mark.parametrize(
    "test_case",
    [
        AttachmentRunIdTestCase(
            description="sql_hook_renders_run_id",
            model_path="models/marts/run_stamp.sql",
            model_sql=(
                "MODEL (\n"
                "  materialized table,\n"
                '  description "Run stamp",\n'
                '  post_hooks [inline_sql("CREATE TABLE IF NOT EXISTS run_log AS SELECT '
                "'@@CTX:run.id' AS run_id\")],\n"
                ");\n\n"
                "SELECT 1 AS order_id\n"
            ),
            expected_warm_attachment_counts=(13, 0, 2),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_reading_run_id_when_compiling_warm_then_each_compile_renders_its_own_run_id(
    cache_invalidation_project: Path, test_case: AttachmentRunIdTestCase
) -> None:
    project_dir: Path = cache_invalidation_project
    write_project_file(project_dir, test_case.model_path, test_case.model_sql)
    env: dict[str, str] = {COMPILE_CACHE_REGION_ENV_VAR: "east"}

    first_run_ids: frozenset[str] = compile_manifest_run_ids(project_dir=project_dir, env=env)
    second_run_ids: frozenset[str] = compile_manifest_run_ids(project_dir=project_dir, env=env)
    warm: CompileCacheOutcome = compile_cache_outcome(project_dir=project_dir, env=env)

    assert (len(first_run_ids), len(second_run_ids)) == (1, 1)
    assert first_run_ids != second_run_ids
    assert outcome_attachment_counts(warm) == test_case.expected_warm_attachment_counts


@pytest.mark.parametrize(
    "test_case",
    [
        AttachmentDiagnosticReplayTestCase(
            description="macro_generated_reference",
            files={
                "models/marts/_sqlbuild/_macros/orders_base.py": (
                    "def orders_base() -> str:\n"
                    "    return 'SELECT order_id FROM __ref(\"stg_orders\")'\n"
                ),
                "models/marts/order_summary.sql": (
                    'MODEL (description "Order summary");\n\n@orders_base()\n'
                ),
            },
            expected_diagnostic_codes=("P006",),
            expected_warm_attachment_counts=(14, 0, 1),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_attachment_diagnostics_when_compiling_warm_then_cache_hit_replays_them(
    cache_invalidation_project: Path, test_case: AttachmentDiagnosticReplayTestCase
) -> None:
    project_dir: Path = cache_invalidation_project
    write_project_files(project_dir, test_case.files)
    env: dict[str, str] = {COMPILE_CACHE_REGION_ENV_VAR: "east"}

    cold: dict[str, Any] = compile_json_payload(project_dir=project_dir, env=env)
    warm: dict[str, Any] = compile_json_payload(project_dir=project_dir, env=env)
    warm_outcome: CompileCacheOutcome = compile_cache_outcome(project_dir=project_dir, env=env)
    reference: CompileCacheOutcome = compile_cache_outcome(
        project_dir=project_dir, env=env, compile_args=("--no-cache",)
    )

    assert tuple(item["code"] for item in warm["diagnostics"]) == (
        test_case.expected_diagnostic_codes
    )
    assert warm["diagnostics"] == cold["diagnostics"]
    assert attachment_cache_counts(warm["compile_timings"]) == (
        test_case.expected_warm_attachment_counts
    )
    assert warm_outcome[:3] == reference[:3]


@pytest.mark.parametrize(
    "test_case",
    [
        AttachmentReferencePolicyTestCase(
            description="macro_generated_reference_policy_toggle",
            files={
                "models/marts/_sqlbuild/_macros/orders_base.py": (
                    "def orders_base() -> str:\n"
                    "    return 'SELECT order_id FROM __ref(\"stg_orders\")'\n"
                ),
                "models/marts/order_summary.sql": (
                    'MODEL (description "Order summary");\n\n@orders_base()\n'
                ),
            },
            relax=lambda root: replace_project_text(
                root,
                "sqlbuild_project.toml",
                "[settings]",
                "[references]\nenforce_explicit = false\n\n[settings]",
            ),
            restore=lambda root: replace_project_text(
                root,
                "sqlbuild_project.toml",
                "[references]\nenforce_explicit = false\n\n[settings]",
                "[settings]",
            ),
            expected_strict_codes=("P006",),
            expected_relaxed_codes=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_replayed_diagnostic_when_reference_policy_toggles_then_matches_uncached_reference(
    cache_invalidation_project: Path, test_case: AttachmentReferencePolicyTestCase
) -> None:
    project_dir: Path = cache_invalidation_project
    write_project_files(project_dir, test_case.files)
    env: dict[str, str] = {COMPILE_CACHE_REGION_ENV_VAR: "east"}
    _ = compile_json_payload(project_dir=project_dir, env=env)
    strict_warm: dict[str, Any] = compile_json_payload(project_dir=project_dir, env=env)

    test_case.relax(project_dir)
    relaxed: CompileCacheOutcome = compile_cache_outcome(project_dir=project_dir, env=env)
    relaxed_reference: CompileCacheOutcome = compile_cache_outcome(
        project_dir=project_dir, env=env, compile_args=("--no-cache",)
    )
    relaxed_rewarm: dict[str, Any] = compile_json_payload(project_dir=project_dir, env=env)
    test_case.restore(project_dir)
    restored: CompileCacheOutcome = compile_cache_outcome(project_dir=project_dir, env=env)
    restored_reference: CompileCacheOutcome = compile_cache_outcome(
        project_dir=project_dir, env=env, compile_args=("--no-cache",)
    )
    restored_rewarm: dict[str, Any] = compile_json_payload(project_dir=project_dir, env=env)

    assert tuple(item["code"] for item in strict_warm["diagnostics"]) == (
        test_case.expected_strict_codes
    )
    assert tuple(item["code"] for item in relaxed_rewarm["diagnostics"]) == (
        test_case.expected_relaxed_codes
    )
    assert tuple(item["code"] for item in restored_rewarm["diagnostics"]) == (
        test_case.expected_strict_codes
    )
    assert relaxed[:3] == relaxed_reference[:3]
    assert restored[:3] == restored_reference[:3]
    assert attachment_cache_counts(restored_rewarm["compile_timings"])[1] == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
