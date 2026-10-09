"""Generated projects and engine views for native project assembly parity."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable
from operator import methodcaller
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile._helpers.assembly import project as project_module
from sqlbuild.compiler.compile._helpers.assembly.project import assemble_compiled_project
from sqlbuild.compiler.compile.constants import COMPILE_INPUT_READS
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import (
    CompileAdapterContext,
    CompiledProject,
    CompileProjectInputs,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.frontier.types import CompilerEngine
from sqlbuild.sql_values.types import CollectionRendering
from tests.integration.src.sqlbuild.compiler.analysis_session.helpers import deferral_kinds

_PYTHON_RESOURCE_FUNCTIONS: tuple[str, ...] = (
    "_build_source_relation_entry",
    "build_seed_relation_target",
    "validate_sql_syntax",
    "validate_hook_sql_syntax",
    "model_build_deps",
    "function_build_deps",
    "audit_scope_deps",
)
_ASSEMBLY_RECORD_PREFIX: str = "project_assembly:"
_ADAPTER_CONTEXT: CompileAdapterContext = CompileAdapterContext(
    value_renderer=DuckDbAdapter(),
    collection_rendering=CollectionRendering.VALUE_LIST,
    python_functions_inherit_default_namespace=True,
    sql_lexical_syntax=DuckDbAdapter.sql_lexical_syntax,
)
_DEFAULTS: tuple[str, ...] = (
    "",
    'seed_schema = "raw"\n',
    'database = "db_${env_name}"\nschema = "main"\n',
    'seed_database = "${n}"\nseed_schema = "seeds_${env_name}"\n',
)
_TARGETS: tuple[str, ...] = (
    'schema = "dev_${env_name}"\nloader_schema = "loaders"\n',
    'database = "wh_${n}"\nschema = "main"\n',
    'schema = "dev"\n',
    'database = "wh"\nschema = "analytics"\nloader_schema = "raw_${flag}"\n',
    "schema = \"${coalesce(ENV:SQB_ASSEMBLY_UNSET, 'main')}\"\n"
    'loader_schema = "${ENV:SQB_ASSEMBLY_LOADERS}"\n',
)
_SEED_NAMESPACES: tuple[str, ...] = (
    "",
    "    schema: seeds_${env_name}\n",
    '    schema: "${CTX:model.name}_s"\n',
    '    database: "${n}"\n    schema: "${CTX:model.database}_x"\n',
    '    schema: "${flag}"\n',
    '    schema: "${ENV:SQB_ASSEMBLY_LOADERS}_${CTX:model.alias}"\n',
)
_SOURCE_NAMESPACES: tuple[str, ...] = ("", "    schema: landing\n", "    database: lake\n")
_HOOKS: tuple[str, ...] = (
    "",
    '  pre_hooks [inline_sql("SELECT 0 AS n")],\n',
    "  post_hooks [inline_sql('SELECT 1'), inline_sql('SELECT 2')],\n",
    "  pre_hooks [inline_sql('SELECT 3')],\n  post_hooks [inline_sql('SELECT 4')],\n",
)
_AUDITS: tuple[str, ...] = ("", "  columns (n (audits [not_null])),\n")


def generated_assembly_files(*, rng: random.Random, model_count: int) -> dict[str, str]:
    """Return a project with managed sources, templated seeds, hooks, audits and a function."""

    references: list[str] = [
        '__source("raw_orders")',
        '__source("landing_orders")',
        '__seed("countries")',
        '__seed("regions")',
        *[f'__ref("orders_{index}")' for index in range(model_count - 1)],
    ]
    models: dict[str, str] = {
        f"models/orders_{index}.sql": (
            f'MODEL (\n  description "Generated orders model {index}",\n'
            f"{rng.choice(_HOOKS)}{rng.choice(_AUDITS)});\n\n"
            f"SELECT 1 AS n FROM {rng.choice(references[: 4 + index])}\n"
        )
        for index in range(model_count)
    }
    return {
        "sqlbuild_project.toml": (
            'name = "assembly"\nadapter = "duckdb"\ndefault_target = "dev"\n\n'
            '[connection]\ndatabase = ":memory:"\n\n'
            '[vars]\nenv_name = "prod"\nn = "3"\nflag = "true"\n\n'
            f"[defaults]\n{rng.choice(_DEFAULTS)}\n[targets.dev]\n{rng.choice(_TARGETS)}"
        ),
        "seeds/lookups.yml": (
            "seeds:\n"
            f"  - name: countries\n    description: Countries.\n{rng.choice(_SEED_NAMESPACES)}"
            "    columns:\n      - name: n\n        type: INTEGER\n"
            f"  - name: regions\n    description: Regions.\n{rng.choice(_SEED_NAMESPACES)}"
            "    columns:\n      - name: n\n        type: INTEGER\n"
        ),
        "seeds/countries.csv": "n\n1\n",
        "seeds/regions.csv": "n\n2\n",
        "sources/raw.yml": (
            "sources:\n"
            "  - name: raw_orders\n    description: Raw orders.\n    managed: true\n"
            f"    write_strategy: table\n{rng.choice(_SOURCE_NAMESPACES)}"
            "    columns:\n      - name: n\n        type: INTEGER\n"
            "  - name: landing_orders\n    description: Landing orders.\n"
            f"{rng.choice(_SOURCE_NAMESPACES)}"
            "    columns:\n      - name: n\n        type: INTEGER\n"
        ),
        "python/loaders/raw.py": (
            "from sqlbuild.loaders import loader\n\n\n"
            "@loader\ndef raw_orders(ctx):\n    '''Load raw orders.'''\n    return [{'n': 1}]\n"
        ),
        "functions/sql/order_numbers.sql": (
            'FUNCTION (\n  description "Order numbers.",\n  arguments (p_n INTEGER),\n'
            "  returns table (n INTEGER)\n);\n\n"
            'SELECT n FROM __ref("orders_0") WHERE n = p_n\n'
        ),
        **models,
    }


def seed_yml(schema: str) -> str:
    """Return a one-seed declaration whose schema is `schema`."""

    return (
        "seeds:\n  - name: countries\n    description: Countries.\n"
        f'    schema: "{schema}"\n    columns:\n      - name: n\n        type: INTEGER\n'
    )


def project_inputs(*, project_dir: Path, files: dict[str, str]) -> CompileProjectInputs:
    """Write `files` and attach their compile inputs as the compile pipeline does."""

    _ = [
        _write(path=project_dir / relative_path, contents=contents)
        for relative_path, contents in files.items()
    ]
    return build_compile_inputs(
        discovered_inputs=discover_project_inputs(project_dir=project_dir),
        adapter_context=_ADAPTER_CONTEXT,
        run_id="integration_run",
        defer_model_sql_validation=True,
    )


def assemble_with(
    *, inputs: CompileProjectInputs, engine: CompilerEngine, monkeypatch: pytest.MonkeyPatch
) -> CompiledProject:
    """Assemble `inputs` with `engine`."""

    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine.value)
    return assemble_compiled_project(inputs=inputs)


def recorded_assembly(
    *, inputs: CompileProjectInputs, engine: CompilerEngine, monkeypatch: pytest.MonkeyPatch
) -> tuple[object, tuple[tuple[str, ...], bool]]:
    """Assemble `inputs` with `engine`; return its assembly view and the input reads recorded."""

    with COMPILE_INPUT_READS.recording() as reads:
        project: CompiledProject = assemble_with(
            inputs=inputs, engine=engine, monkeypatch=monkeypatch
        )
    return assembly_view(project), (reads.environment_names, reads.read_run_id)


def assembly_view(project: CompiledProject) -> object:
    """Return every resource fact native project assembly derives, with the diagnostics."""

    return (
        tuple((model.name, model.deps, model.destination) for model in project.models),
        tuple(source.source_entry for source in project.sources),
        tuple(seed.destination for seed in project.seeds),
        tuple((function.name, function.deps) for function in project.functions),
        tuple((audit.name, audit.scope_deps) for audit in project.audits),
        project.diagnostics,
    )


def assembly_deferrals(record_dir: Path) -> Counter[str]:
    """Count the project assembly `site:kind` deferral records below `record_dir`."""

    return Counter(
        filter(
            methodcaller("startswith", _ASSEMBLY_RECORD_PREFIX),
            deferral_kinds(record_dir).elements(),
        )
    )


def python_resource_calls(*, monkeypatch: pytest.MonkeyPatch) -> Counter[str]:
    """Count calls to Python's resource-fact functions from project assembly."""

    calls: Counter[str] = Counter()
    _ = [
        monkeypatch.setattr(
            project_module,
            name,
            _counted(name=name, function=getattr(project_module, name), calls=calls),
        )
        for name in _PYTHON_RESOURCE_FUNCTIONS
    ]
    return calls


def _write(*, path: Path, contents: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.write_text(contents, encoding="utf-8")


def _counted(*, name: str, function: Callable[..., Any], calls: Counter[str]) -> Callable[..., Any]:
    def counted(*args: Any, **kwargs: Any) -> Any:
        calls[name] += 1
        return function(*args, **kwargs)

    return counted
