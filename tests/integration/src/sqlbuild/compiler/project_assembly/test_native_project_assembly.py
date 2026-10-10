"""Native project assembly equals Python's resource assembly, or hands the project back."""

from __future__ import annotations

import os
import random
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompiledProject, CompileProjectInputs
from sqlbuild.compiler.frontier.types import CompilerEngine
from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR
from tests.integration.src.sqlbuild.compiler.helpers import mismatches
from tests.integration.src.sqlbuild.compiler.project_assembly._test_types import (
    AssemblyDeferralTestCase,
    DeferredAssemblyTestCase,
    GeneratedAssemblyParityTestCase,
    OptOutTestCase,
    WindowsEnvironmentTestCase,
)
from tests.integration.src.sqlbuild.compiler.project_assembly.helpers import (
    DEFERRED_PROJECT_FACTS,
    DEFERRED_SYNTAX_CHECK,
    assemble_with,
    assembly_deferrals,
    assembly_view,
    generated_assembly_files,
    project_inputs,
    python_resource_calls,
    recorded_assembly,
    rejected_opt_outs,
    seed_yml,
    windows_environ,
)

_PROJECT_TOML: str = (
    'name = "assembly"\nadapter = "duckdb"\n\n[connection]\ndatabase = ":memory:"\n\n'
)
_ORDERS_MODEL: str = 'MODEL (description "Orders");\n\nSELECT 1 AS n\n'
_REQUIRED_ANALYSIS_TOML: str = (
    'name = "assembly"\nadapter = "duckdb"\n\n'
    '[connection]\ndatabase = ":memory:"\n\n[settings]\nrequire_sql_analysis = true\n'
)
_OPT_OUT_HEADER: str = 'MODEL (\n  description "Orders",\n  sql_analysis false,\n'
_SEED_FILES: dict[str, str] = {
    "seeds/countries.csv": "n\n1\n",
    "models/orders.sql": _ORDERS_MODEL,
}


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedAssemblyParityTestCase(
            description="managed sources, templated seeds and targets, hooks, audits, a function",
            seed=20261009,
            count=8,
            model_count=12,
            environment={"SQB_ASSEMBLY_LOADERS": "loaders"},
            expected_minimum_python_calls=200,
            expected_minimum_environment_reads=4,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_projects_when_assembling_natively_then_matches_python(
    test_case: GeneratedAssemblyParityTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_dir: Path = tmp_path / "records"
    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))
    _ = [monkeypatch.setenv(name, value) for name, value in test_case.environment.items()]
    calls: Counter[str] = python_resource_calls(monkeypatch=monkeypatch)
    rng: random.Random = random.Random(test_case.seed)
    inputs: list[CompileProjectInputs] = [
        project_inputs(
            project_dir=tmp_path / f"project_{index}",
            files=generated_assembly_files(rng=rng, model_count=test_case.model_count),
        )
        for index in range(test_case.count)
    ]
    python: list[tuple[object, tuple[tuple[str, ...], bool]]] = [
        recorded_assembly(
            inputs=item,
            engine=CompilerEngine.NATIVE,
            monkeypatch=monkeypatch,
            deferred=DEFERRED_PROJECT_FACTS,
        )
        for item in inputs
    ]
    python_calls: int = calls.total()
    native: list[tuple[object, tuple[tuple[str, ...], bool]]] = [
        recorded_assembly(
            inputs=item, engine=CompilerEngine.NATIVE_PREVIEW, monkeypatch=monkeypatch
        )
        for item in inputs
    ]

    assert (
        mismatches(
            inputs=list(range(test_case.count)),
            expected=list[object](python),
            actual=list[object](native),
        )
        == []
    )
    assert sum(len(reads[0]) for _, reads in native) >= test_case.expected_minimum_environment_reads
    assert python_calls >= test_case.expected_minimum_python_calls
    assert calls.total() == python_calls
    assert assembly_deferrals(record_dir) == Counter()


@pytest.mark.parametrize(
    "test_case",
    [
        AssemblyDeferralTestCase(
            description="model SQL the parser rejects",
            files={
                "sqlbuild_project.toml": _PROJECT_TOML,
                "models/orders.sql": 'MODEL (description "Orders");\n\nSELECT FROM WHERE (\n',
            },
            expected_kind=None,
            expected_error="SQL syntax error in model 'orders'",
        ),
        AssemblyDeferralTestCase(
            description="hook SQL the parser rejects",
            files={
                "sqlbuild_project.toml": _PROJECT_TOML,
                "models/orders.sql": (
                    'MODEL (\n  description "Orders",\n  pre_hooks [inline_sql("SELECT FROM (")],\n'
                    ");\n\nSELECT 1 AS n\n"
                ),
            },
            expected_kind=None,
            expected_error="Polyglot could not parse model 'orders' pre_hooks[0]",
        ),
        AssemblyDeferralTestCase(
            description="a seed schema reading an unset environment variable",
            files={
                "sqlbuild_project.toml": _PROJECT_TOML,
                "seeds/lookups.yml": seed_yml("${ENV:SQB_UNSET_SEED_SCHEMA}"),
                **_SEED_FILES,
            },
            expected_kind="target_template",
            expected_error="references missing ENV variable 'SQB_UNSET_SEED_SCHEMA'",
        ),
        AssemblyDeferralTestCase(
            description="a preserved target schema the seed does not own",
            files={
                "sqlbuild_project.toml": (
                    'name = "assembly"\nadapter = "duckdb"\ndefault_target = "dev"\n\n'
                    '[connection]\ndatabase = ":memory:"\n\n[targets.dev]\nschema = "preserve"\n'
                ),
                "seeds/lookups.yml": (
                    "seeds:\n  - name: countries\n    description: Countries.\n"
                    "    columns:\n      - name: n\n        type: INTEGER\n"
                ),
                "seeds/countries.csv": "n\n1\n",
                "models/orders.sql": (
                    'MODEL (description "Orders", schema "orders");\n\nSELECT 1 AS n\n'
                ),
            },
            expected_kind="preserved_namespace",
            expected_error="Seed 'countries' has no logical schema",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_projects_python_rejects_when_assembling_natively_then_raises_python_error(
    test_case: AssemblyDeferralTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_dir: Path = tmp_path / "records"
    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))
    inputs: CompileProjectInputs = project_inputs(project_dir=tmp_path, files=test_case.files)

    with pytest.raises(CompileInputError) as python_error:
        _ = assemble_with(
            inputs=inputs,
            engine=CompilerEngine.NATIVE,
            monkeypatch=monkeypatch,
            deferred=DEFERRED_PROJECT_FACTS,
        )
    with pytest.raises(CompileInputError) as native_error:
        _ = assemble_with(
            inputs=inputs, engine=CompilerEngine.NATIVE_PREVIEW, monkeypatch=monkeypatch
        )

    assert test_case.expected_error in str(python_error.value)
    assert str(native_error.value) == str(python_error.value)
    assert assembly_deferrals(record_dir) == (
        Counter({f"project_assembly:{test_case.expected_kind}": 1})
        if test_case.expected_kind is not None
        else Counter()
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DeferredAssemblyTestCase(
            description="a seed schema reading a list variable",
            effective_vars={"tags": ["daily"]},
            seed_schema="${tags}",
            expected_schema="['daily']",
            expected_kind="target_template",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_a_variable_only_python_renders_when_assembling_natively_then_python_assembles(
    test_case: DeferredAssemblyTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_dir: Path = tmp_path / "records"
    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))
    inputs: CompileProjectInputs = replace(
        project_inputs(
            project_dir=tmp_path,
            files={
                "sqlbuild_project.toml": _PROJECT_TOML,
                "seeds/lookups.yml": seed_yml(test_case.seed_schema),
                **_SEED_FILES,
            },
        ),
        effective_vars=test_case.effective_vars,
    )

    python: CompiledProject = assemble_with(
        inputs=inputs,
        engine=CompilerEngine.NATIVE,
        monkeypatch=monkeypatch,
        deferred=DEFERRED_PROJECT_FACTS,
    )
    native: CompiledProject = assemble_with(
        inputs=inputs, engine=CompilerEngine.NATIVE_PREVIEW, monkeypatch=monkeypatch
    )

    assert assembly_view(native) == assembly_view(python)
    assert native.seeds[0].destination.schema == test_case.expected_schema
    assert assembly_deferrals(record_dir) == (
        Counter({f"project_assembly:{test_case.expected_kind}": 1})
        if test_case.expected_kind is not None
        else Counter()
    )


@pytest.mark.parametrize(
    "test_case",
    [
        WindowsEnvironmentTestCase(
            description="a lower-case ENV name Windows resolves to an upper-case variable",
            environment={"APP_SCHEMA": "landing"},
            seed_schema="${coalesce(ENV:app_schema, 'main')}",
            expected_schema="landing",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_windows_environment_when_assembling_natively_then_env_lookups_match_python(
    test_case: WindowsEnvironmentTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_dir: Path = tmp_path / "records"
    monkeypatch.setattr(os, "environ", windows_environ(test_case.environment))
    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))
    inputs: CompileProjectInputs = project_inputs(
        project_dir=tmp_path,
        files={
            "sqlbuild_project.toml": _PROJECT_TOML,
            "seeds/lookups.yml": seed_yml(test_case.seed_schema),
            **_SEED_FILES,
        },
    )

    python: CompiledProject = assemble_with(
        inputs=inputs,
        engine=CompilerEngine.NATIVE,
        monkeypatch=monkeypatch,
        deferred=DEFERRED_PROJECT_FACTS,
    )
    native: CompiledProject = assemble_with(
        inputs=inputs, engine=CompilerEngine.NATIVE_PREVIEW, monkeypatch=monkeypatch
    )

    assert python.seeds[0].destination.schema == test_case.expected_schema
    assert assembly_view(native) == assembly_view(python)
    assert assembly_deferrals(record_dir) == Counter()


@pytest.mark.parametrize(
    "test_case",
    [
        OptOutTestCase(
            description="parseable, unparseable and unparseable-hook opt-outs",
            models={
                "models/parses.sql": f"{_OPT_OUT_HEADER});\n\nSELECT 1 AS n\n",
                "models/broken_query.sql": f"{_OPT_OUT_HEADER});\n\nSELECT FROM WHERE (\n",
                "models/broken_hook.sql": (
                    f'{_OPT_OUT_HEADER}  post_hooks [inline_sql("SELECT FROM (")],\n);\n\n'
                    "SELECT 1 AS n\n"
                ),
            },
            expected_rejected={"broken_hook": False, "broken_query": False, "parses": True},
            expected_python_validations=7,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sql_analysis_opt_outs_when_attaching_natively_then_python_rejections_match(
    test_case: OptOutTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_dir: Path = tmp_path / "records"
    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))
    files: dict[str, str] = {"sqlbuild_project.toml": _REQUIRED_ANALYSIS_TOML, **test_case.models}

    python: tuple[dict[str, bool], int] = rejected_opt_outs(
        project_dir=tmp_path / "python",
        files=files,
        engine=CompilerEngine.NATIVE,
        monkeypatch=monkeypatch,
        deferred=DEFERRED_SYNTAX_CHECK,
    )
    native: tuple[dict[str, bool], int] = rejected_opt_outs(
        project_dir=tmp_path / "native",
        files=files,
        engine=CompilerEngine.NATIVE_PREVIEW,
        monkeypatch=monkeypatch,
    )

    assert python == (test_case.expected_rejected, test_case.expected_python_validations)
    assert native == (test_case.expected_rejected, 0)
    assert assembly_deferrals(record_dir) == Counter()
