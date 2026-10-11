"""Native project assembly equals Python's recorded resource assembly and its errors."""

from __future__ import annotations

import os
import random
from collections import Counter
from pathlib import Path

import pytest

import sqlbuild._native as native_module
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.assembly.project import assemble_compiled_project
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileProjectInputs
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.frontier.types import CompilerEngine
from sqlbuild.compiler.project_assembly.types import ProjectRequestRow
from tests.integration.src.sqlbuild.compiler.helpers import (
    GoldenEntry,
    golden_differences,
    golden_entry,
    golden_name,
    read_golden,
)
from tests.integration.src.sqlbuild.compiler.project_assembly._test_types import (
    AssemblyDeferralTestCase,
    EdgeAssemblyTestCase,
    GeneratedAssemblyParityTestCase,
    GraphFactsTestCase,
    NativePanicTestCase,
    OptOutTestCase,
    WindowsEnvironmentTestCase,
)
from tests.integration.src.sqlbuild.compiler.project_assembly.helpers import (
    EDGE_ASSEMBLY_PROJECTS,
    assemble_with,
    assembly_outcome,
    generated_assembly_files,
    project_inputs,
    python_resource_calls,
    record_assembly_requests,
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
            expected_minimum_environment_reads=4,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_projects_when_assembling_natively_then_matches_python_golden(
    test_case: GeneratedAssemblyParityTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = [monkeypatch.setenv(name, value) for name, value in test_case.environment.items()]
    calls: Counter[str] = python_resource_calls(monkeypatch=monkeypatch)
    rng: random.Random = random.Random(test_case.seed)
    project_dirs: list[Path] = [tmp_path / f"project_{index}" for index in range(test_case.count)]
    inputs: list[CompileProjectInputs] = [
        project_inputs(
            project_dir=project_dir,
            files=generated_assembly_files(rng=rng, model_count=test_case.model_count),
        )
        for project_dir in project_dirs
    ]
    native: list[tuple[object, tuple[tuple[str, ...], bool]]] = [
        recorded_assembly(inputs=item, engine=CompilerEngine.NATIVE, monkeypatch=monkeypatch)
        for item in inputs
    ]
    golden: list[GoldenEntry] = [
        golden_entry("project_assembly", view, masked=(str(project_dir),))
        for project_dir, view in zip(project_dirs, native, strict=True)
    ]

    assert (
        golden_differences(
            read_golden(golden_name("project_assembly", test_case.description)), golden
        )
        == []
    )
    assert sum(len(reads[0]) for _, reads in native) >= test_case.expected_minimum_environment_reads
    assert calls == Counter()


@pytest.mark.parametrize(
    "test_case",
    [
        EdgeAssemblyTestCase(
            description="error and python value edges",
            projects=EDGE_ASSEMBLY_PROJECTS,
            expected_raised=22,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_projects_python_rejects_when_assembling_natively_then_matches_python_golden(
    test_case: EdgeAssemblyTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SQB_EDGE_UNSET", raising=False)
    project_dirs: list[Path] = [
        tmp_path / f"edge_{index}" for index in range(len(test_case.projects))
    ]
    outcomes: list[tuple[object, ...]] = [
        assembly_outcome(
            project_dir=project_dir,
            files=files,
            effective_vars=effective_vars,
            monkeypatch=monkeypatch,
        )
        for project_dir, (_, files, effective_vars) in zip(
            project_dirs, test_case.projects, strict=True
        )
    ]
    golden: list[GoldenEntry] = [
        golden_entry("project_assembly", outcome, masked=(str(project_dir),))
        for project_dir, outcome in zip(project_dirs, outcomes, strict=True)
    ]

    assert (
        golden_differences(
            read_golden(golden_name("project_assembly", test_case.description)), golden
        )
        == []
    )
    assert sum(outcome[0] != "ok" for outcome in outcomes) == test_case.expected_raised


@pytest.mark.parametrize(
    "test_case",
    [
        AssemblyDeferralTestCase(
            description="model SQL the parser rejects",
            files={
                "sqlbuild_project.toml": _PROJECT_TOML,
                "models/orders.sql": 'MODEL (description "Orders");\n\nSELECT FROM WHERE (\n',
            },
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
            expected_error="Polyglot could not parse model 'orders' pre_hooks[0]",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_sql_the_parser_rejects_when_assembling_then_raises_python_error(
    test_case: AssemblyDeferralTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs: CompileProjectInputs = project_inputs(project_dir=tmp_path, files=test_case.files)

    with pytest.raises(CompileInputError) as raised:
        _ = assemble_with(inputs=inputs, engine=CompilerEngine.NATIVE, monkeypatch=monkeypatch)

    assert test_case.expected_error in str(raised.value)


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
    monkeypatch.setattr(os, "environ", windows_environ(test_case.environment))
    inputs: CompileProjectInputs = project_inputs(
        project_dir=tmp_path,
        files={
            "sqlbuild_project.toml": _PROJECT_TOML,
            "seeds/lookups.yml": seed_yml(test_case.seed_schema),
            **_SEED_FILES,
        },
    )

    native: CompiledProjectView = assemble_with(
        inputs=inputs, engine=CompilerEngine.NATIVE, monkeypatch=monkeypatch
    )

    assert native.seeds[0].destination.schema == test_case.expected_schema


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
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sql_analysis_opt_outs_when_attaching_natively_then_python_rejections_match(
    test_case: OptOutTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files: dict[str, str] = {"sqlbuild_project.toml": _REQUIRED_ANALYSIS_TOML, **test_case.models}

    native: dict[str, bool] = rejected_opt_outs(
        project_dir=tmp_path / "native",
        files=files,
        engine=CompilerEngine.NATIVE,
        monkeypatch=monkeypatch,
    )

    assert native == test_case.expected_rejected


@pytest.mark.parametrize(
    "test_case",
    [
        GraphFactsTestCase(
            description="tagged models in folders, tagged seeds and both function kinds",
            files={
                "sqlbuild_project.toml": 'name = "orders"\nadapter = "duckdb"\n',
                "models/staging/orders.sql": (
                    "MODEL (description 'Orders.', tags [daily, finance]);\n\nSELECT 1 AS id\n"
                ),
                "models/customers.sql": (
                    "MODEL (description 'Customers.');\n\nSELECT id FROM __ref(\"orders\")\n"
                ),
                "seeds/regions.yml": (
                    "seeds:\n  - name: regions\n    description: Regions.\n"
                    "    tags: [lookup]\n    columns:\n      - name: n\n        type: INTEGER\n"
                ),
                "seeds/regions.csv": "n\n1\n",
                "functions/sql/is_big.sql": (
                    "FUNCTION (description 'Big.', arguments (x INTEGER), returns BOOLEAN,"
                    " tags [math]);\n\nx > 100\n"
                ),
                "functions/sql/order_ids.sql": (
                    "FUNCTION (description 'Ids.', arguments (x INTEGER),"
                    ' returns table (id INTEGER));\n\nSELECT id FROM __ref("orders")\n'
                ),
            },
            expected_model_tags=([], ["daily", "finance"]),
            expected_seeds=[("regions", ["lookup"])],
            expected_function_kinds=("udf", "table_fn"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_project_when_assembling_natively_then_request_carries_graph_facts(
    test_case: GraphFactsTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[ProjectRequestRow] = record_assembly_requests(monkeypatch=monkeypatch)
    project: CompiledProjectView = assemble_with(
        inputs=project_inputs(project_dir=tmp_path / "project", files=test_case.files),
        engine=CompilerEngine.NATIVE,
        monkeypatch=monkeypatch,
    )
    request: ProjectRequestRow = requests[0]

    assert (
        [(name, directory, tags) for name, directory, tags, _, _ in request[5]],
        [(name, tags) for name, tags, _, _ in request[7]],
        [(kind, name, tags) for kind, name, tags, _ in request[8]],
    ) == (
        [
            (model.key.name, str(model.relative_path.parent)) + (tags,)
            for model, tags in zip(project.models, test_case.expected_model_tags, strict=True)
        ],
        test_case.expected_seeds,
        [
            (str(function.key.resource_type), function.key.name, list(function.tags))
            for function in project.functions
        ],
    )
    assert [kind for kind, _, _, _ in request[8]] == list(test_case.expected_function_kinds)


@pytest.mark.parametrize(
    "test_case",
    [
        NativePanicTestCase(
            description="a T-SQL hook the parser panics on",
            files={
                "sqlbuild_project.toml": _PROJECT_TOML,
                "models/orders.sql": (
                    'MODEL (\n  description "Orders",\n'
                    '  pre_hooks [inline_sql("SELECT IF(region > 1, re")],\n);\n\nSELECT 1 AS n\n'
                ),
            },
            dialect="tsql",
            expected_message=(
                "NativeCompilerError: native SQL compilation panicked (native project assembly)"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_native_assembly_panics_when_assembling_then_raises_without_python_retry(
    test_case: NativePanicTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, CompilerEngine.NATIVE.value)
    inputs: CompileProjectInputs = project_inputs(
        project_dir=tmp_path / "project", files=test_case.files
    )
    calls: Counter[str] = python_resource_calls(monkeypatch=monkeypatch)

    with pytest.raises(native_module.NativeCompilerError) as raised:
        _ = assemble_compiled_project(
            inputs=inputs,
            inference_profile=ExpressionInferenceProfile(sql_analysis_dialect=test_case.dialect),
        )

    assert (str(raised.value), calls) == (test_case.expected_message, Counter())
