"""Warm compile-cache reuse must match a cache-disabled compile after every input edit."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from scripts.cold_compile_performance.main.semantic_compile_fingerprint import (
    semantic_compile_fingerprint,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    CompileCacheDisabledTestCase,
    CompileCacheInvalidationTestCase,
    CompileCacheOutcome,
)

_REGION_ENV_VAR: str = "SQB_CACHE_INVALIDATION_REGION"
_TIMING_PATTERN: re.Pattern[str] = re.compile(r"\(\d+(?:\.\d+)?s\)")
_EXTRA_PROJECT_FILES: dict[str, str] = {
    "models/marts/_sqlbuild/_enums/order_channel.sql": 'ENUM (\n  name order_channel,\n  members (WEB "web", PARTNER "partner"),\n);\n',
    "models/marts/_sqlbuild/_constants/min_quantity.sql": "CONSTANT (name min_quantity, value 1);\n",
    "models/marts/channel_orders.sql": (
        "MODEL (\n"
        "  materialized table,\n"
        "  columns (\n"
        "    order_id (nullable false, audits [not_null]),\n"
        "  ),\n"
        ");\n\n"
        "SELECT\n"
        "  o.order_id,\n"
        '  @enum("order_channel").WEB AS order_channel,\n'
        '  o.quantity >= @const("min_quantity") AS meets_minimum,\n'
        "  CAST(@@quantity_multiplier AS INTEGER) * o.quantity AS scaled_quantity,\n"
        "  '@@ENV:" + _REGION_ENV_VAR + "' AS region\n"
        'FROM __ref("stg_orders") o\n'
    ),
    "tests/unit/test_channel_orders.sql": (
        "TEST ();\n\n"
        "WITH\n"
        "__ref__stg_orders AS (\n"
        "  SELECT 1 AS order_id, 2 AS quantity\n"
        "),\n"
        "__expected__channel_orders AS (\n"
        "  SELECT 1 AS order_id, 'web' AS order_channel, TRUE AS meets_minimum\n"
        ")\n"
        "SELECT 1\n"
    ),
}


def _sqb(
    *, project_dir: Path, args: tuple[str, ...], env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(Path(sys.executable).with_name("sqb")),
            "--project-dir",
            str(project_dir),
            "--no-color",
            *args,
        ],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
        check=False,
    )


def _compile(
    *, project_dir: Path, env: dict[str, str], no_cache: bool = False
) -> CompileCacheOutcome:
    result: subprocess.CompletedProcess[str] = _sqb(
        project_dir=project_dir,
        args=("compile", "--json", *(("--no-cache",) if no_cache else ())),
        env=env,
    )
    try:
        payload: object = json.loads(result.stdout)
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return CompileCacheOutcome(
            returncode=result.returncode,
            fingerprint=_TIMING_PATTERN.sub("", result.stderr),
            fact_cache_hits=0,
            fact_cache_misses=0,
        )
    values: dict[str, object] = cast(dict[str, object], payload)
    timings: dict[str, int] = cast(dict[str, int], values.get("compile_timings", {}))
    return CompileCacheOutcome(
        returncode=result.returncode,
        fingerprint=semantic_compile_fingerprint(
            payload=values, compiled_dir=project_dir / "target" / "compiled"
        ),
        fact_cache_hits=timings.get("fact_cache_hits", 0),
        fact_cache_misses=timings.get("fact_cache_misses", 0),
    )


def _replace(project_dir: Path, relative_path: str, old: str, new: str) -> None:
    path: Path = project_dir / relative_path
    contents: str = path.read_text(encoding="utf-8")
    assert old in contents, f"{old!r} not found in {relative_path}"
    path.write_text(contents.replace(old, new, 1), encoding="utf-8")


def _write(project_dir: Path, relative_path: str, contents: str) -> None:
    path: Path = project_dir / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def _move(project_dir: Path, source: str, destination: str) -> None:
    (project_dir / destination).parent.mkdir(parents=True, exist_ok=True)
    (project_dir / source).rename(project_dir / destination)


INVALIDATION_CASES: list[CompileCacheInvalidationTestCase] = [
    CompileCacheInvalidationTestCase(
        description="model_sql_body_edit",
        edit=lambda root: _replace(
            root, "models/staging/stg_orders.sql", "  quantity,", "  quantity + 0 AS quantity,"
        ),
    ),
    CompileCacheInvalidationTestCase(
        description="model_header_metadata_edit",
        edit=lambda root: _replace(
            root,
            "models/staging/stg_orders.sql",
            "customer_id (nullable false, audits [not_null]),",
            'customer_id (nullable false, description "Buyer.", audits [not_null, unique]),',
        ),
    ),
    CompileCacheInvalidationTestCase(
        description="model_header_syntax_error",
        edit=lambda root: _replace(
            root, "models/staging/stg_orders.sql", "materialized view,", "materialized view,,(("
        ),
        expect_failure=True,
    ),
    CompileCacheInvalidationTestCase(
        description="model_added",
        edit=lambda root: _write(
            root,
            "models/marts/order_quantities.sql",
            'MODEL ();\n\nSELECT order_id, quantity FROM __ref("stg_orders")\n',
        ),
    ),
    CompileCacheInvalidationTestCase(
        description="model_deleted",
        edit=lambda root: (root / "models/marts/channel_orders.sql").unlink(),
        expect_failure=True,
    ),
    CompileCacheInvalidationTestCase(
        description="model_moved_between_folders",
        edit=lambda root: _move(
            root, "models/staging/stg_payments.sql", "models/staging/payments/stg_payments.sql"
        ),
    ),
    CompileCacheInvalidationTestCase(
        description="source_yaml_column_type_edit",
        edit=lambda root: _replace(
            root,
            "sources/raw.yml",
            "      - name: quantity\n        type: INTEGER",
            "      - name: quantity\n        type: BIGINT",
        ),
        changes_output=False,
    ),
    CompileCacheInvalidationTestCase(
        description="source_yaml_column_rename",
        edit=lambda root: _replace(
            root,
            "sources/raw.yml",
            "      - name: quantity\n        type: INTEGER",
            "      - name: item_count\n        type: INTEGER",
        ),
        expect_failure=True,
    ),
    CompileCacheInvalidationTestCase(
        description="source_yaml_syntax_error",
        edit=lambda root: _replace(root, "sources/raw.yml", "sources:", "sources: [\n"),
        expect_failure=True,
    ),
    CompileCacheInvalidationTestCase(
        description="unit_test_expected_edit",
        edit=lambda root: _replace(
            root,
            "tests/unit/test_channel_orders.sql",
            "TRUE AS meets_minimum",
            "FALSE AS meets_minimum",
        ),
    ),
    CompileCacheInvalidationTestCase(
        description="unit_test_structure_error",
        edit=lambda root: _replace(root, "tests/unit/test_channel_orders.sql", "SELECT 1\n", ""),
        expect_failure=True,
    ),
    CompileCacheInvalidationTestCase(
        description="project_macro_edit",
        edit=lambda root: _replace(
            root,
            "macros/currency.py",
            'return f"{price_cents} * {quantity}"',
            'return f"({price_cents}) * ({quantity})"',
        ),
    ),
    CompileCacheInvalidationTestCase(
        description="scoped_macro_edit",
        edit=lambda root: _replace(
            root,
            "models/marts/_sqlbuild/_macros/currency.py",
            'return f"ROUND(({column}) / 100.0, 2)"',
            'return f"ROUND(({column}) / 100.0, 3)"',
        ),
    ),
    CompileCacheInvalidationTestCase(
        description="enum_member_value_edit",
        edit=lambda root: _replace(
            root, "models/marts/_sqlbuild/_enums/order_channel.sql", 'WEB "web"', 'WEB "online"'
        ),
    ),
    CompileCacheInvalidationTestCase(
        description="constant_value_edit",
        edit=lambda root: _replace(
            root, "models/marts/_sqlbuild/_constants/min_quantity.sql", "value 1", "value 3"
        ),
    ),
    CompileCacheInvalidationTestCase(
        description="project_var_edit",
        edit=lambda root: _replace(
            root, "sqlbuild_project.toml", 'quantity_multiplier = "2"', 'quantity_multiplier = "5"'
        ),
    ),
    CompileCacheInvalidationTestCase(
        description="target_schema_edit",
        edit=lambda root: _replace(
            root, "sqlbuild_project.toml", 'schema = "dev"', 'schema = "dev_next"'
        ),
    ),
    CompileCacheInvalidationTestCase(
        description="local_config_target_switch",
        edit=lambda root: _write(root, "sqlbuild_local.toml", 'target = "prod"\n'),
    ),
    CompileCacheInvalidationTestCase(
        description="python_loader_edit",
        edit=lambda root: _replace(
            root,
            "python/loaders/waffle_sources.py",
            "from sqlbuild.loaders import loader\n",
            "from sqlbuild.loaders import loader\n\nLOADER_REVISION: int = 2\n",
        ),
        changes_output=False,
    ),
    CompileCacheInvalidationTestCase(
        description="environment_variable_edit",
        edit=lambda root: None,
        edited_env={_REGION_ENV_VAR: "west"},
    ),
]


@pytest.fixture
def cache_invalidation_project(tmp_path: Path) -> Path:
    project_dir: Path = tmp_path / "orders_project"
    result: subprocess.CompletedProcess[str] = _sqb(
        project_dir=tmp_path, args=("playground", str(project_dir)), env={}
    )
    assert result.returncode == 0, result.stdout + result.stderr
    shutil.rmtree(project_dir / "target", ignore_errors=True)
    for relative_path, contents in _EXTRA_PROJECT_FILES.items():
        _write(project_dir, relative_path, contents)
    _replace(
        project_dir,
        "sqlbuild_project.toml",
        "[settings]",
        '[vars]\nquantity_multiplier = "2"\n\n[settings]',
    )
    return project_dir


@pytest.mark.parametrize(
    "test_case", INVALIDATION_CASES, ids=[case.description for case in INVALIDATION_CASES]
)
def test_given_warm_compile_cache_when_input_changes_then_output_matches_cache_disabled_compile(
    cache_invalidation_project: Path, test_case: CompileCacheInvalidationTestCase
) -> None:
    project_dir: Path = cache_invalidation_project
    initial_env: dict[str, str] = {_REGION_ENV_VAR: "east"}
    cold: CompileCacheOutcome = _compile(project_dir=project_dir, env=initial_env)
    warm: CompileCacheOutcome = _compile(project_dir=project_dir, env=initial_env)
    assert cold.returncode == 0
    assert cold.fact_cache_misses > 0
    assert warm == CompileCacheOutcome(
        returncode=0,
        fingerprint=cold.fingerprint,
        fact_cache_hits=cold.fact_cache_misses,
        fact_cache_misses=0,
    )

    test_case.edit(project_dir)
    edited_env: dict[str, str] = {**initial_env, **test_case.edited_env}
    edited: CompileCacheOutcome = _compile(project_dir=project_dir, env=edited_env)
    reference: CompileCacheOutcome = _compile(
        project_dir=project_dir, env=edited_env, no_cache=True
    )
    rewarmed: CompileCacheOutcome = _compile(project_dir=project_dir, env=edited_env)

    assert (edited.returncode != 0) is test_case.expect_failure
    assert (edited.returncode, edited.fingerprint) == (reference.returncode, reference.fingerprint)
    assert (rewarmed.returncode, rewarmed.fingerprint) == (
        reference.returncode,
        reference.fingerprint,
    )
    if not test_case.expect_failure:
        assert edited.fingerprint != cold.fingerprint or not test_case.changes_output
        assert rewarmed.fact_cache_misses == 0


DISABLED_CACHE_CASES: list[CompileCacheDisabledTestCase] = [
    CompileCacheDisabledTestCase(description="no_cache_flag", compile_args=("--no-cache",)),
    CompileCacheDisabledTestCase(
        description="disable_environment_variable",
        env={"SQLBUILD_DISABLE_COMPILE_CACHE": "1"},
    ),
    CompileCacheDisabledTestCase(
        description="target_compile_cache_false",
        edit=lambda root: _replace(
            root, "sqlbuild_project.toml", 'schema = "dev"', 'schema = "dev"\ncompile_cache = false'
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case", DISABLED_CACHE_CASES, ids=[case.description for case in DISABLED_CACHE_CASES]
)
def test_given_disabled_compile_cache_when_compiling_then_no_facts_are_read_or_written(
    cache_invalidation_project: Path, test_case: CompileCacheDisabledTestCase
) -> None:
    project_dir: Path = cache_invalidation_project
    test_case.edit(project_dir)
    env: dict[str, str] = {_REGION_ENV_VAR: "east", **test_case.env}

    for _ in range(2):
        result: subprocess.CompletedProcess[str] = _sqb(
            project_dir=project_dir, args=("compile", "--json", *test_case.compile_args), env=env
        )
        assert result.returncode == 0, result.stderr
        timings: dict[str, int] = json.loads(result.stdout)["compile_timings"]
        assert (timings["fact_cache_hits"], timings["fact_cache_misses"]) == (0, 0)

    assert not list((project_dir / "target").rglob("facts-v*"))
