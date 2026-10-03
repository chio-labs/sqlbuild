"""Warm compile-cache reuse must match a cache-disabled compile after every input edit."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    CompileCacheDisabledTestCase,
    CompileCacheInvalidationTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    COMPILE_CACHE_REGION_ENV_VAR,
    COMPILE_CACHE_UNEXPANDED_MODEL_COUNT,
    DESCRIBED_HOOK_DECORATOR,
    CompileCacheOutcome,
    add_project_provider,
    compile_cache_outcome,
    install_custom_duckdb_adapter,
    move_project_file,
    replace_project_text,
    rewrite_python_hook,
    run_installed_sqb,
    write_project_file,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CompileCacheInvalidationTestCase(
            description="model_sql_body_edit",
            edit=lambda root: replace_project_text(
                root, "models/staging/stg_orders.sql", "  quantity,", "  quantity + 0 AS quantity,"
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="model_header_metadata_edit",
            edit=lambda root: replace_project_text(
                root,
                "models/staging/stg_orders.sql",
                "customer_id (nullable false, audits [not_null]),",
                'customer_id (nullable false, description "Buyer.", audits [not_null, unique]),',
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="model_header_syntax_error",
            edit=lambda root: replace_project_text(
                root, "models/staging/stg_orders.sql", "materialized view,", "materialized view,,(("
            ),
            expected_failure=True,
        ),
        CompileCacheInvalidationTestCase(
            description="model_added",
            edit=lambda root: write_project_file(
                root,
                "models/marts/order_quantities.sql",
                'MODEL (description "Test model order_quantities.");\n\nSELECT order_id, quantity FROM __ref("stg_orders")\n',
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="model_deleted",
            edit=lambda root: (root / "models/marts/channel_orders.sql").unlink(),
            expected_failure=True,
        ),
        CompileCacheInvalidationTestCase(
            description="model_moved_between_folders",
            edit=lambda root: move_project_file(
                root, "models/staging/stg_payments.sql", "models/staging/payments/stg_payments.sql"
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="source_yaml_column_type_edit",
            edit=lambda root: replace_project_text(
                root,
                "sources/raw.yml",
                "      - name: quantity\n        type: INTEGER",
                "      - name: quantity\n        type: BIGINT",
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="source_yaml_column_rename",
            edit=lambda root: replace_project_text(
                root,
                "sources/raw.yml",
                "      - name: quantity\n        type: INTEGER",
                "      - name: item_count\n        type: INTEGER",
            ),
            expected_failure=True,
        ),
        CompileCacheInvalidationTestCase(
            description="source_yaml_syntax_error",
            edit=lambda root: replace_project_text(
                root, "sources/raw.yml", "sources:", "sources: [\n"
            ),
            expected_failure=True,
        ),
        CompileCacheInvalidationTestCase(
            description="unit_test_expected_edit",
            edit=lambda root: replace_project_text(
                root,
                "tests/unit/test_channel_orders.sql",
                "TRUE AS meets_minimum",
                "FALSE AS meets_minimum",
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="second_test_block_in_multi_block_file_edit",
            edit=lambda root: replace_project_text(
                root,
                "tests/unit/test_channel_blocks.sql",
                "SELECT 2 AS order_id, 'web' AS order_channel",
                "SELECT 2 AS order_id, 'partner' AS order_channel",
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="unit_test_structure_error",
            edit=lambda root: replace_project_text(
                root, "tests/unit/test_channel_orders.sql", "SELECT 1\n", ""
            ),
            expected_failure=True,
        ),
        CompileCacheInvalidationTestCase(
            description="project_macro_edit",
            edit=lambda root: replace_project_text(
                root,
                "macros/currency.py",
                'return f"{price_cents} * {quantity}"',
                'return f"({price_cents}) * ({quantity})"',
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="scoped_macro_edit",
            edit=lambda root: replace_project_text(
                root,
                "models/marts/_sqlbuild/_macros/currency.py",
                'return f"ROUND(({column}) / 100.0, 2)"',
                'return f"ROUND(({column}) / 100.0, 3)"',
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="enum_member_value_edit",
            edit=lambda root: replace_project_text(
                root, "models/marts/_sqlbuild/_enums/order_channel.sql", 'WEB "web"', 'WEB "online"'
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="constant_value_edit",
            edit=lambda root: replace_project_text(
                root, "models/marts/_sqlbuild/_constants/min_quantity.sql", "value 1", "value 3"
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="project_var_edit",
            edit=lambda root: replace_project_text(
                root,
                "sqlbuild_project.toml",
                'quantity_multiplier = "2"',
                'quantity_multiplier = "5"',
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="target_schema_edit",
            edit=lambda root: replace_project_text(
                root, "sqlbuild_project.toml", 'schema = "dev"', 'schema = "dev_next"'
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="local_config_target_switch",
            edit=lambda root: write_project_file(root, "sqlbuild_local.toml", 'target = "prod"\n'),
        ),
        CompileCacheInvalidationTestCase(
            description="python_loader_edit",
            edit=lambda root: replace_project_text(
                root,
                "python/loaders/waffle_sources.py",
                "from sqlbuild.loaders import loader\n",
                "from sqlbuild.loaders import loader\n\nLOADER_REVISION: int = 2\n",
            ),
            expected_output_change=False,
        ),
        CompileCacheInvalidationTestCase(
            description="environment_variable_edit",
            edit=lambda root: None,
            edited_env={COMPILE_CACHE_REGION_ENV_VAR: "west"},
        ),
        CompileCacheInvalidationTestCase(
            description="project_defaults_edit",
            edit=lambda root: replace_project_text(
                root,
                "sqlbuild_project.toml",
                '[defaults]\nmaterialized = "table"',
                '[defaults]\nmaterialized = "table"\ntags = ["nightly"]',
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="path_defaults_edit",
            edit=lambda root: replace_project_text(
                root,
                "sqlbuild_project.toml",
                '[path_defaults.staging]\nmaterialized = "view"',
                '[path_defaults.staging]\nmaterialized = "view"\nalias = "${CTX:model.name}_v2"',
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="cli_vars_edit",
            edit=lambda root: None,
            edited_compile_args=("--vars", '{"quantity_multiplier": "7"}'),
        ),
        CompileCacheInvalidationTestCase(
            description="project_settings_edit",
            edit=lambda root: replace_project_text(
                root,
                "sqlbuild_project.toml",
                'default_audit_severity = "warn"',
                'default_audit_severity = "warn"\nsql_analysis = false',
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="adapter_dialect_edit",
            edit=lambda root: replace_project_text(
                root, "sqlbuild_project.toml", 'adapter = "duckdb"', 'adapter = "postgres"'
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="scoped_macro_import_edit",
            edit=lambda root: replace_project_text(
                root,
                "models/marts/_sqlbuild/_macros/scaling.py",
                'line_total_cents(column, "2")',
                'line_total_cents(column, "3")',
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="enum_member_added",
            edit=lambda root: replace_project_text(
                root,
                "models/marts/_sqlbuild/_enums/order_channel.sql",
                'PARTNER "partner"',
                'PARTNER "partner", STORE "store"',
            ),
            expected_output_change=False,
        ),
        CompileCacheInvalidationTestCase(
            description="model_schema_declaration_edit",
            edit=lambda root: replace_project_text(
                root,
                "models/marts/_sqlbuild/_schemas/order_metric.sql",
                'description "Scaled order quantities"',
                'description "Order quantities scaled for reporting"',
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="named_sql_hook_edit",
            edit=lambda root: replace_project_text(
                root,
                "models/marts/_sqlbuild/_hooks/sql/record_orders.sql",
                "COUNT(*) AS row_count",
                "COUNT(*) AS written_rows",
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="python_hook_signature_edit",
            edit=lambda root: replace_project_text(
                root,
                "models/marts/_sqlbuild/_hooks/python/notifications.py",
                'def notify_complete(ctx, channel="#orders"):',
                'def notify_complete(ctx, channel="#orders", *, priority):',
            ),
            expected_failure=True,
        ),
        CompileCacheInvalidationTestCase(
            description="audit_factory_edit",
            edit=lambda root: replace_project_text(
                root,
                "python/audits/order_quality.py",
                "scaled_quantity >= 0",
                "scaled_quantity >= 1",
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="no_sql_analysis_flag",
            edit=lambda root: None,
            edited_compile_args=("--no-sql-analysis",),
        ),
        CompileCacheInvalidationTestCase(
            description="project_sql_analysis_reenabled",
            setup=lambda root: replace_project_text(
                root,
                "sqlbuild_project.toml",
                'default_audit_severity = "warn"',
                'default_audit_severity = "warn"\nsql_analysis = false',
            ),
            edit=lambda root: replace_project_text(
                root,
                "sqlbuild_project.toml",
                'default_audit_severity = "warn"\nsql_analysis = false',
                'default_audit_severity = "warn"',
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="custom_materialization_removed",
            edit=lambda root: (root / "materializations/partition_tracked.py").unlink(),
            expected_failure=True,
        ),
        CompileCacheInvalidationTestCase(
            description="provider_name_conflicts_with_hook_argument",
            setup=lambda root: rewrite_python_hook(
                root, decorator=DESCRIBED_HOOK_DECORATOR, parameters="ctx, **kwargs"
            ),
            edit=lambda root: add_project_provider(root, "channel"),
            expected_failure=True,
        ),
        CompileCacheInvalidationTestCase(
            description="project_adapter_rendering_edit",
            setup=install_custom_duckdb_adapter,
            edit=lambda root: replace_project_text(
                root,
                "adapters/duckdb_plus.py",
                'return f"{rendered}"',
                'return f"({rendered})"',
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="python_hook_reads_edit",
            edit=lambda root: rewrite_python_hook(
                root,
                decorator=(
                    '@hook(reads=model("stg_customers"), description="Notify that orders completed")'
                ),
                parameters='ctx, channel="#orders"',
            ),
        ),
        CompileCacheInvalidationTestCase(
            description="python_hook_provider_usage_edit",
            setup=lambda root: add_project_provider(root, "order_notifier"),
            edit=lambda root: rewrite_python_hook(
                root,
                decorator=DESCRIBED_HOOK_DECORATOR,
                parameters='ctx, order_notifier, channel="#orders"',
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_warm_compile_cache_when_input_changes_then_output_matches_cache_disabled_compile(
    cache_invalidation_project: Path, test_case: CompileCacheInvalidationTestCase
) -> None:
    project_dir: Path = cache_invalidation_project
    test_case.setup(project_dir)
    initial_env: dict[str, str] = {COMPILE_CACHE_REGION_ENV_VAR: "east"}
    cold: CompileCacheOutcome = compile_cache_outcome(project_dir=project_dir, env=initial_env)
    warm: CompileCacheOutcome = compile_cache_outcome(project_dir=project_dir, env=initial_env)
    assert cold.returncode == 0
    assert cold.fact_cache_misses > 0
    assert warm == CompileCacheOutcome(
        returncode=0,
        diagnostics=cold.diagnostics,
        fingerprint=cold.fingerprint,
        fact_cache_hits=cold.fact_cache_misses,
        fact_cache_misses=0,
        attachment_cache_hits=cold.attachment_cache_misses
        - 1
        - COMPILE_CACHE_UNEXPANDED_MODEL_COUNT,
        attachment_cache_misses=0,
        attachment_cache_bypasses=1,
        attachment_cache_unexpanded_bypasses=COMPILE_CACHE_UNEXPANDED_MODEL_COUNT,
    )

    test_case.edit(project_dir)
    edited_env: dict[str, str] = {**initial_env, **test_case.edited_env}
    edited_args: tuple[str, ...] = test_case.edited_compile_args
    edited: CompileCacheOutcome = compile_cache_outcome(
        project_dir=project_dir, env=edited_env, compile_args=edited_args
    )
    reference: CompileCacheOutcome = compile_cache_outcome(
        project_dir=project_dir, env=edited_env, compile_args=("--no-cache", *edited_args)
    )
    rewarmed: CompileCacheOutcome = compile_cache_outcome(
        project_dir=project_dir, env=edited_env, compile_args=edited_args
    )

    assert (edited.returncode != 0) is test_case.expected_failure
    assert (
        (edited.diagnostics, edited.fingerprint) != (cold.diagnostics, cold.fingerprint)
    ) is test_case.expected_output_change
    assert edited[:3] == reference[:3]
    assert rewarmed[:3] == reference[:3]
    assert rewarmed.fact_cache_misses == test_case.expected_rewarmed_fact_cache_misses
    assert rewarmed.attachment_cache_misses == 0


@pytest.mark.parametrize(
    "test_case",
    [
        CompileCacheDisabledTestCase(description="no_cache_flag", compile_args=("--no-cache",)),
        CompileCacheDisabledTestCase(
            description="disable_environment_variable",
            env={"SQLBUILD_DISABLE_COMPILE_CACHE": "1"},
        ),
        CompileCacheDisabledTestCase(
            description="target_compile_cache_false",
            edit=lambda root: replace_project_text(
                root,
                "sqlbuild_project.toml",
                'schema = "dev"',
                'schema = "dev"\ncompile_cache = false',
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_disabled_compile_cache_when_compiling_then_no_facts_are_read_or_written(
    cache_invalidation_project: Path, test_case: CompileCacheDisabledTestCase
) -> None:
    project_dir: Path = cache_invalidation_project
    test_case.edit(project_dir)
    env: dict[str, str] = {COMPILE_CACHE_REGION_ENV_VAR: "east", **test_case.env}

    first: subprocess.CompletedProcess[str] = run_installed_sqb(
        project_dir=project_dir, args=("compile", "--json", *test_case.compile_args), env=env
    )
    second: subprocess.CompletedProcess[str] = run_installed_sqb(
        project_dir=project_dir, args=("compile", "--json", *test_case.compile_args), env=env
    )

    assert (first.returncode, second.returncode) == (0, 0), first.stderr + second.stderr
    first_timings: dict[str, int] = json.loads(first.stdout)["compile_timings"]
    second_timings: dict[str, int] = json.loads(second.stdout)["compile_timings"]
    assert (
        first_timings["fact_cache_hits"],
        first_timings["fact_cache_misses"],
    ) == test_case.expected_fact_cache_counts
    assert (
        second_timings["fact_cache_hits"],
        second_timings["fact_cache_misses"],
    ) == test_case.expected_fact_cache_counts
    assert tuple((project_dir / "target").rglob("facts-v*")) == test_case.expected_fact_databases
