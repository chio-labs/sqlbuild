"""E2E tests for sqb diff command."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.diff._test_types import (
    DiffCommandE2ETestCase,
    DiffJsonOutputE2ETestCase,
    DiffKeyFailureE2ETestCase,
    DiffSamplingPrecedenceE2ETestCase,
    DiffSamplingSeedE2ETestCase,
    VirtualDiffE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.diff.helpers import (
    build_both_environments,
    changed_key_examples,
    execute_duckdb,
    prepare_diff_project,
    run_sampled_diff,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_project_toml,
    build_virtual_plan_repo_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        DiffCommandE2ETestCase(
            description="identical full diff returns zero",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "orders_snapshot",
                "No schema differences.",
                "No changed columns.",
            ),
        ),
        DiffCommandE2ETestCase(
            description="deterministic sample reports non exhaustive comparison scope",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--sample-rows",
                "2",
                "--sample-seed",
                "7",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "sampled 2 of 3 union keys (66.67%; seed 7)",
                "Sampled Rows",
                "No changed columns in sampled keys.",
                "prod     3  <not bounded by cursor>",
                "dev      3  <not bounded by cursor>",
            ),
        ),
        DiffCommandE2ETestCase(
            description="sample limit above population reports exhaustive comparison",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--sample-rows",
                "10",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "exhaustive (3 union keys; configured sample limit 10)",
                "Rows",
                "No changed columns.",
            ),
        ),
        DiffCommandE2ETestCase(
            description="non positive cli sample limit fails clearly",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--sample-rows",
                "0",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=1,
            expected_stderr_fragments=("diff --sample-rows must be positive",),
        ),
        DiffCommandE2ETestCase(
            description="conflicting sample and exhaustive overrides fail clearly",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--sample-rows",
                "2",
                "--exhaustive",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=1,
            expected_stderr_fragments=("diff --exhaustive cannot be combined with --sample-rows",),
        ),
        DiffCommandE2ETestCase(
            description="model safety limit fails before comparison",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--max-models",
                "1",
                "--select",
                "orders_snapshot",
                "customer_totals",
            ),
            expected_exit_code=1,
            expected_stderr_fragments=("diff selected 2 models, exceeding --max-models 1",),
        ),
        DiffCommandE2ETestCase(
            description="column safety limit fails before row comparison",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--max-columns",
                "4",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=1,
            expected_stderr_fragments=(
                "model 'orders_snapshot' has 5 columns, exceeding --max-columns 4",
            ),
        ),
        DiffCommandE2ETestCase(
            description="partial cursor coverage warns and continues with union sample",
            mutation_sql=("DELETE FROM dev.orders_snapshot WHERE order_id = 1",),
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--bounded",
                "10000d",
                "--sample-rows",
                "2",
                "--sample-seed",
                "7",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=1,
            expected_stdout_fragments=(
                "sampled 2 of 3 union keys (66.67%; seed 7)",
                "Warning: cursor coverage differs between sides",
                "comparison continued without narrowing the requested bounds",
                "prod only",
                "order_id=1",
            ),
        ),
        DiffCommandE2ETestCase(
            description="row mismatch returns nonzero and reports column mismatch",
            mutation_sql=(
                "UPDATE dev.orders_snapshot SET amount_cents = amount_cents + 5 WHERE order_id = 1",
            ),
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=1,
            expected_stdout_fragments=(
                "joined: 3",
                "unequal",
                "amount_cents",
                "mismatches=1",
                "order_id=1 | 100 -> 105",
            ),
        ),
        DiffCommandE2ETestCase(
            description="concise side only samples are shown by default",
            mutation_sql=(
                "DELETE FROM dev.orders_sparse WHERE order_id = 1",
                "INSERT INTO dev.orders_sparse (order_id, customer_id) VALUES (99, 9)",
            ),
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--select",
                "orders_sparse",
            ),
            expected_exit_code=1,
            expected_stdout_fragments=(
                "prod only",
                "order_id=1",
                "dev only",
                "order_id=99",
            ),
        ),
        DiffCommandE2ETestCase(
            description="concise multi column examples show multiple changed columns",
            mutation_sql=(
                (
                    "UPDATE dev.orders_snapshot SET customer_id = 99, "
                    "amount_cents = amount_cents + 5 WHERE order_id = 1"
                ),
            ),
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=1,
            expected_stdout_fragments=(
                "customer_id",
                "amount_cents",
                "order_id=1 | 1 -> 99",
                "order_id=1 | 100 -> 105",
            ),
        ),
        DiffCommandE2ETestCase(
            description="verbose diff shows example row changes",
            mutation_sql=(
                "UPDATE dev.orders_snapshot SET amount_cents = amount_cents + 5 WHERE order_id = 1",
            ),
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--verbose",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=1,
            expected_stdout_fragments=(
                "Examples",
                "order_id=1 | 100 -> 105",
            ),
        ),
        DiffCommandE2ETestCase(
            description="verbose diff shows side only key samples",
            mutation_sql=(
                "DELETE FROM dev.orders_sparse WHERE order_id = 1",
                "INSERT INTO dev.orders_sparse (order_id, customer_id) VALUES (99, 9)",
            ),
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--verbose",
                "--select",
                "orders_sparse",
            ),
            expected_exit_code=1,
            expected_stdout_fragments=(
                "prod only",
                "order_id=1",
                "dev only",
                "order_id=99",
            ),
        ),
        DiffCommandE2ETestCase(
            description="excluded column changes are ignored",
            mutation_sql=(
                "UPDATE dev.orders_snapshot SET status = 'surprising' WHERE order_id = 1",
            ),
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=("No changed columns.",),
        ),
        DiffCommandE2ETestCase(
            description="tolerance pass stays clean",
            mutation_sql=(
                "UPDATE dev.orders_snapshot SET amount_cents = amount_cents + 1 WHERE order_id = 1",
            ),
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=("No changed columns.",),
        ),
        DiffCommandE2ETestCase(
            description="tolerance fail reports mismatch",
            mutation_sql=(
                "UPDATE dev.orders_snapshot SET amount_cents = amount_cents + 2 WHERE order_id = 1",
            ),
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=1,
            expected_stdout_fragments=(
                "amount_cents",
                "mismatches=1",
                "order_id=1 | 100 -> 102",
            ),
        ),
        DiffCommandE2ETestCase(
            description="multi model output uses global header and divider",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--select",
                "orders_snapshot",
                "customer_totals",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "selected models: 2",
                "orders_snapshot",
                "customer_totals",
                "────────────────",
            ),
        ),
        DiffCommandE2ETestCase(
            description="example caps can be overridden",
            mutation_sql=(
                "UPDATE dev.orders_snapshot SET amount_cents = amount_cents + 5 WHERE order_id = 1",
                "UPDATE dev.orders_snapshot SET amount_cents = amount_cents + 7 WHERE order_id = 2",
            ),
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--max-column-examples",
                "2",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=1,
            expected_stdout_fragments=(
                "order_id=1 | 100 -> 105",
                "order_id=2 | 200 -> 207",
            ),
        ),
        DiffCommandE2ETestCase(
            description="schema only ignores row drift",
            mutation_sql=(
                "UPDATE dev.orders_snapshot SET amount_cents = amount_cents + 5 WHERE order_id = 1",
            ),
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--schema-only",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=("No schema differences.", "order_id"),
        ),
        DiffCommandE2ETestCase(
            description="bounded fallback on cursorless model succeeds",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--bounded",
                "30d",
                "--select",
                "customer_totals",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "Fallback",
                "no cursor configured; used full row diff",
                "No changed columns.",
            ),
        ),
        DiffCommandE2ETestCase(
            description="missing unique key fails clearly",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--select",
                "daily_revenue",
            ),
            expected_exit_code=1,
            expected_stderr_fragments=("model 'daily_revenue' requires unique_key for row diff",),
        ),
        DiffCommandE2ETestCase(
            description="environment schemas auto-create through real cli build flow",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=("orders_snapshot",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_diff_project_when_running_diff_then_behavior_matches_expected(
    test_case: DiffCommandE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_diff_project(tmp_path)
    build_both_environments(project_dir=project_dir)
    db_path: Path = project_dir / "diff.duckdb"

    mutation_sql: str
    for mutation_sql in test_case.mutation_sql:
        execute_duckdb(db_path=db_path, sql=mutation_sql)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout, result.stdout + result.stderr
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr, result.stdout + result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        DiffSamplingPrecedenceE2ETestCase(
            description="model and cli sampling override path and project defaults",
            project_limit=1,
            project_seed=3,
            path_limit=2,
            path_seed=5,
            model_limit=3,
            model_seed=7,
            cli_limit=2,
            cli_seed=11,
            expected_model_scope="exhaustive (3 union keys; configured sample limit 3)",
            expected_model_exhaustive_scope="exhaustive (3 union keys)",
            expected_path_scope="sampled 2 of 3 union keys (66.67%; seed 5)",
            expected_project_scope="sampled 1 of 3 union keys (33.33%; seed 3)",
            expected_cli_scope="sampled 2 of 3 union keys (66.67%; seed 11)",
            expected_exhaustive_scope="exhaustive (3 union keys)",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_layered_sampling_config_when_diffing_then_model_and_cli_precedence_apply(
    test_case: DiffSamplingPrecedenceE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_diff_project(tmp_path)
    project_config_path: Path = project_dir / "sqlbuild_project.toml"
    project_config: str = project_config_path.read_text(encoding="utf-8")
    project_config = project_config.replace(
        '[defaults]\nmaterialized = "table"',
        f'[defaults]\nmaterialized = "table"\nrow_diff_sample_rows = '
        f"{test_case.project_limit}\nrow_diff_sample_seed = {test_case.project_seed}",
    )
    project_config += (
        "\n[path_defaults.intermediate]\n"
        f"row_diff_sample_rows = {test_case.path_limit}\n"
        f"row_diff_sample_seed = {test_case.path_seed}\n"
    )
    project_config_path.write_text(project_config, encoding="utf-8")
    model_path: Path = project_dir / "models/intermediate/orders_snapshot.sql"
    model_sql: str = model_path.read_text(encoding="utf-8")
    model_sql = model_sql.replace(
        "  cursor_type timestamp,",
        f"  cursor_type timestamp,\n  row_diff_sample_rows {test_case.model_limit},\n"
        f"  row_diff_sample_seed {test_case.model_seed},",
    )
    model_path.write_text(model_sql, encoding="utf-8")
    build_both_environments(project_dir=project_dir)

    model_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "diff", "prod:dev", "--full", "--select", "orders_snapshot"),
        project_dir=project_dir,
    )

    assert model_result.returncode == 0, model_result.stdout + model_result.stderr
    assert test_case.expected_model_scope in model_result.stdout

    inherited_disabled_sql: str = model_sql.replace(
        f"  row_diff_sample_rows {test_case.model_limit},\n"
        f"  row_diff_sample_seed {test_case.model_seed},",
        "  row_diff_sample_rows 0,",
    )
    model_path.write_text(inherited_disabled_sql, encoding="utf-8")
    model_exhaustive_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "diff", "prod:dev", "--full", "--select", "orders_snapshot"),
        project_dir=project_dir,
    )

    assert model_exhaustive_result.returncode == 0, (
        model_exhaustive_result.stdout + model_exhaustive_result.stderr
    )
    assert test_case.expected_model_exhaustive_scope in model_exhaustive_result.stdout
    assert "configured sample limit" not in model_exhaustive_result.stdout

    model_path.write_text(
        model_sql.replace(
            f"  row_diff_sample_rows {test_case.model_limit},\n"
            f"  row_diff_sample_seed {test_case.model_seed},\n",
            "",
        ),
        encoding="utf-8",
    )
    path_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "diff", "prod:dev", "--full", "--select", "orders_snapshot"),
        project_dir=project_dir,
    )

    assert path_result.returncode == 0, path_result.stdout + path_result.stderr
    assert test_case.expected_path_scope in path_result.stdout

    project_config_path.write_text(
        project_config.replace(
            "\n[path_defaults.intermediate]\n"
            f"row_diff_sample_rows = {test_case.path_limit}\n"
            f"row_diff_sample_seed = {test_case.path_seed}\n",
            "\n",
        ),
        encoding="utf-8",
    )
    project_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "diff", "prod:dev", "--full", "--select", "orders_snapshot"),
        project_dir=project_dir,
    )

    assert project_result.returncode == 0, project_result.stdout + project_result.stderr
    assert test_case.expected_project_scope in project_result.stdout

    cli_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "diff",
            "prod:dev",
            "--full",
            "--sample-rows",
            str(test_case.cli_limit),
            "--sample-seed",
            str(test_case.cli_seed),
            "--select",
            "orders_snapshot",
        ),
        project_dir=project_dir,
    )

    assert cli_result.returncode == 0, cli_result.stdout + cli_result.stderr
    assert test_case.expected_cli_scope in cli_result.stdout

    exhaustive_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "diff",
            "prod:dev",
            "--full",
            "--exhaustive",
            "--select",
            "orders_snapshot",
        ),
        project_dir=project_dir,
    )

    assert exhaustive_result.returncode == 0, exhaustive_result.stdout + exhaustive_result.stderr
    assert test_case.expected_exhaustive_scope in exhaustive_result.stdout
    assert "configured sample limit" not in exhaustive_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DiffSamplingSeedE2ETestCase(
            description="same seed repeats membership and alternate seed changes it",
            row_limit=2,
            repeated_seed=7,
            alternate_seed=11,
            expected_membership_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_changed_population_when_sampling_then_seed_membership_is_reproducible(
    test_case: DiffSamplingSeedE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_diff_project(tmp_path)
    build_both_environments(project_dir=project_dir)
    execute_duckdb(
        db_path=project_dir / "diff.duckdb",
        sql="UPDATE dev.orders_snapshot SET amount_cents = amount_cents + 10",
    )

    first_result: subprocess.CompletedProcess[str] = run_sampled_diff(
        project_dir=project_dir,
        model_name="orders_snapshot",
        row_limit=test_case.row_limit,
        seed=test_case.repeated_seed,
    )
    repeated_result: subprocess.CompletedProcess[str] = run_sampled_diff(
        project_dir=project_dir,
        model_name="orders_snapshot",
        row_limit=test_case.row_limit,
        seed=test_case.repeated_seed,
    )
    alternate_result: subprocess.CompletedProcess[str] = run_sampled_diff(
        project_dir=project_dir,
        model_name="orders_snapshot",
        row_limit=test_case.row_limit,
        seed=test_case.alternate_seed,
    )

    assert first_result.returncode == 1, first_result.stdout + first_result.stderr
    assert repeated_result.returncode == 1, repeated_result.stdout + repeated_result.stderr
    assert alternate_result.returncode == 1, alternate_result.stdout + alternate_result.stderr
    first_keys: tuple[str, ...] = changed_key_examples(output=first_result.stdout)
    repeated_keys: tuple[str, ...] = changed_key_examples(output=repeated_result.stdout)
    alternate_keys: tuple[str, ...] = changed_key_examples(output=alternate_result.stdout)
    assert first_keys == repeated_keys
    assert first_keys != alternate_keys
    assert len(first_keys) == test_case.expected_membership_count
    assert len(alternate_keys) == test_case.expected_membership_count


@pytest.mark.parametrize(
    "test_case",
    [
        DiffJsonOutputE2ETestCase(
            description="sampled diff writes explicit structured scope and coverage",
            row_limit=2,
            seed=7,
            expected_status="no_differences_found",
            expected_scope="sampled",
            expected_population=3,
            expected_compared=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_json_output_path_when_sampling_then_document_reports_evaluated_scope(
    test_case: DiffJsonOutputE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_diff_project(tmp_path)
    build_both_environments(project_dir=project_dir)
    output_path: Path = project_dir / "diff-result.json"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "diff",
            "prod:dev",
            "--full",
            "--sample-rows",
            str(test_case.row_limit),
            "--sample-seed",
            str(test_case.seed),
            "--json-output",
            str(output_path),
            "--select",
            "orders_snapshot",
        ),
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload: dict[str, object] = cast(
        dict[str, object], json.loads(output_path.read_text(encoding="utf-8"))
    )
    assert payload["status"] == test_case.expected_status
    models: list[dict[str, object]] = cast(list[dict[str, object]], payload["models"])
    model: dict[str, object] = models[0]
    assert model["comparison_scope"] == test_case.expected_scope
    sampling: dict[str, object] = cast(dict[str, object], model["sampling"])
    assert sampling["population_keys"] == test_case.expected_population
    assert sampling["compared_keys"] == test_case.expected_compared
    coverage: dict[str, object] = cast(dict[str, object], model["coverage"])
    from_coverage: dict[str, object] = cast(dict[str, object], coverage["from"])
    to_coverage: dict[str, object] = cast(dict[str, object], coverage["to"])
    assert from_coverage["row_count"] == test_case.expected_population
    assert to_coverage["row_count"] == test_case.expected_population


@pytest.mark.parametrize(
    "test_case",
    [
        DiffCommandE2ETestCase(
            description="schema diff ignores unused from connection credentials",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--schema-only",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=("No schema differences.",),
        ),
        DiffCommandE2ETestCase(
            description="full diff ignores unused from connection credentials",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=("No changed columns.",),
        ),
        DiffCommandE2ETestCase(
            description="bounded diff ignores unused from connection credentials",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--bounded",
                "30d",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=("No changed columns.",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unused_from_connection_when_diffing_then_to_connection_is_authoritative(
    test_case: DiffCommandE2ETestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = prepare_diff_project(tmp_path)
    build_both_environments(project_dir=project_dir)
    project_config_path: Path = project_dir / "sqlbuild_project.toml"
    original_project_config: str = project_config_path.read_text(encoding="utf-8")
    rewritten_project_config: str = original_project_config.replace(
        '[targets.prod]\nschema = "prod"',
        '[targets.prod]\nschema = "prod"\n\n[targets.prod.connection]\n'
        'database = "${ENV:SQLBUILD_TEST_UNUSED_FROM_DATABASE}"',
    )
    assert rewritten_project_config != original_project_config
    project_config_path.write_text(
        rewritten_project_config,
        encoding="utf-8",
    )
    monkeypatch.delenv("SQLBUILD_TEST_UNUSED_FROM_DATABASE", raising=False)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout, result.stdout + result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        DiffCommandE2ETestCase(
            description="missing to connection credential fails before inspection",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--schema-only",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=1,
            expected_stderr_fragments=(
                "effective connection references missing ENV variable "
                "'SQLBUILD_TEST_MISSING_TO_DATABASE'",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_missing_to_connection_credential_when_diffing_then_it_fails_before_inspection(
    test_case: DiffCommandE2ETestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = prepare_diff_project(tmp_path)
    build_both_environments(project_dir=project_dir)
    project_config_path: Path = project_dir / "sqlbuild_project.toml"
    original_project_config: str = project_config_path.read_text(encoding="utf-8")
    rewritten_project_config: str = original_project_config.replace(
        '[targets.dev]\nschema = "dev"',
        '[targets.dev]\nschema = "dev"\n\n[targets.dev.connection]\n'
        'database = "${ENV:SQLBUILD_TEST_MISSING_TO_DATABASE}"',
    )
    assert rewritten_project_config != original_project_config
    project_config_path.write_text(rewritten_project_config, encoding="utf-8")
    monkeypatch.delenv("SQLBUILD_TEST_MISSING_TO_DATABASE", raising=False)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr, result.stdout + result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        DiffKeyFailureE2ETestCase(
            description="null unique key fails clearly",
            mutation_sql=("UPDATE dev.orders_snapshot SET order_id = NULL WHERE order_id = 3",),
            expected_stderr_fragment="row diff right relation contains null unique_key values",
        ),
        DiffKeyFailureE2ETestCase(
            description="duplicate unique key fails clearly",
            mutation_sql=("UPDATE dev.orders_snapshot SET order_id = 2 WHERE order_id = 3",),
            expected_stderr_fragment="row diff right relation contains duplicate unique_key values",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_dev_keys_when_running_diff_then_it_fails_clearly(
    test_case: DiffKeyFailureE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_diff_project(tmp_path)
    build_both_environments(project_dir=project_dir)
    db_path: Path = project_dir / "diff.duckdb"

    mutation_sql: str
    for mutation_sql in test_case.mutation_sql:
        execute_duckdb(db_path=db_path, sql=mutation_sql)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "diff",
            "prod:dev",
            "--full",
            "--select",
            "orders_snapshot",
        ),
        project_dir=project_dir,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert test_case.expected_stderr_fragment in result.stderr, result.stdout + result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualDiffE2ETestCase(
            description="whole VDE diff allows finalized VDE stale against workspace",
            command=("--no-color", "diff", "dev:pr", "--schema-only"),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "Virtual diff",
                "working VDEs            no",
                "selected models         3",
                "compared models         2",
                "unchanged refs skipped  1",
                "SQLBuild Diff Summary",
            ),
        ),
        VirtualDiffE2ETestCase(
            description="allow partial diff compares working VDEs",
            command=(
                "--no-color",
                "diff",
                "dev:pr",
                "--schema-only",
                "--allow-partial-diff",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "Virtual diff",
                "working VDEs            no",
                "selected models         3",
                "compared models         2",
                "unchanged refs skipped  1",
                "SQLBuild Diff Summary",
            ),
        ),
        VirtualDiffE2ETestCase(
            description="unchanged virtual refs are skipped",
            command=(
                "--no-color",
                "diff",
                "dev:pr",
                "--schema-only",
                "--allow-partial-diff",
                "--select",
                "dim_customers",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "selected models         1",
                "compared models         0",
                "unchanged refs skipped  1",
                "No VDE ref differences in selected scope.",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_diff_with_working_vde_when_running_then_it_respects_partial_guard(
    test_case: VirtualDiffE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_diff_guard",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    default_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert default_build_result.returncode == 0, default_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    branch_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )
    assert branch_build_result.returncode == 0, branch_build_result.stderr

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout, result.stdout + result.stderr
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr, result.stdout + result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualDiffE2ETestCase(
            description="verbose virtual diff keeps persisted source identity current",
            command=(
                "--no-color",
                "diff",
                "dev:pr",
                "--schema-only",
                "--verbose",
                "--select",
                "source_orders",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "selected models         1",
                "unchanged refs skipped  1",
            ),
            unexpected_stdout_fragments=("not current with workspace",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_source_dependent_vdes_when_diffing_verbose_then_refs_are_workspace_current(
    test_case: VirtualDiffE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_diff_source_identity",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    schema: raw\n"
                "    table: raw_orders\n"
                "    freshness:\n"
                "      strategy: column\n"
                "      column: data_version\n"
                "      type: integer\n"
            ),
            "models/source_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "CREATE SCHEMA raw; "
            "CREATE TABLE raw.raw_orders (id INTEGER, data_version INTEGER); "
            "INSERT INTO raw.raw_orders VALUES (1, 1)"
        ),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    dev_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert dev_build_result.returncode == 0, dev_build_result.stdout + dev_build_result.stderr
    pr_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr", "--changes-only"),
        project_dir=project_dir,
    )
    assert pr_build_result.returncode == 0, pr_build_result.stdout + pr_build_result.stderr

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout, result.stdout
    for fragment in test_case.unexpected_stdout_fragments:
        assert fragment not in result.stdout, result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualDiffE2ETestCase(
            description="active VDE requires partial diff flag",
            command=("--no-color", "diff", "dev:pr", "--schema-only"),
            expected_exit_code=1,
            expected_stderr_fragments=(
                "whole-VDE virtual diff requires finalized VDEs",
                "non-finalized VDEs: pr",
                "--allow-partial-diff",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_diff_with_active_vde_when_running_whole_diff_then_requires_partial_flag(
    test_case: VirtualDiffE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_diff_active_guard",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    default_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert default_build_result.returncode == 0, default_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    branch_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr", "--select", "stg_orders"),
        project_dir=project_dir,
    )
    assert branch_build_result.returncode == 0, branch_build_result.stderr

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr
