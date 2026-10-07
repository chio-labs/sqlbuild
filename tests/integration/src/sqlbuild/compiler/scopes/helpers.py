"""Scoped projects and engine-parity outcomes for the native declaration scope tests."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile._helpers.attachment.declaration_scope import build_declaration_scope
from sqlbuild.compiler.compile._helpers.render.macros import load_project_macros
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import DeclarationScopeBuild, LoadedMacro
from sqlbuild.compiler.discovery.exceptions import DiscoveryError
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.scopes.main._open_native_scope_index import open_native_scope_index
from sqlbuild.compiler.scopes.main.load_or_build_scope_index import load_or_build_scope_index
from sqlbuild.compiler.scopes.models import ScopeIndex, ScopeLookup
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax

PROJECT_CONFIG: str = (
    'name = "scope_parity"\nadapter = "duckdb"\n\n[connection]\ndatabase = "scope.duckdb"\n'
)
RAW_SOURCES: str = (
    "sources:\n  - name: raw_orders\n    description: Orders feed.\n"
    "    expression: >-\n      (SELECT 1 AS order_id)\n"
)
SCOPED_PROJECT: dict[str, str] = {
    "sqlbuild_project.toml": PROJECT_CONFIG,
    "sources/raw.yml": RAW_SOURCES,
    "macros/money.py": 'def cents(value: str) -> str:\n    return f"{value} * 100"\n',
    "enums/status.sql": "ENUM (name order_status, members [PLACED, SHIPPED]);\n",
    "models/sales/_sqlbuild/macros/labels.py": (
        "def sales_label(value: str) -> str:\n    return f\"'sales:' || {value}\"\n"
    ),
    "models/sales/_sqlbuild/constants/limits.sql": "CONSTANT (name sales_cap, value 3);\n",
    "models/sales/eu/_macros/rates.py": (
        'def eu_rate(value: str) -> str:\n    return f"{value} * 2"\n'
    ),
    "models/sales/eu/_enums/region.sql": "ENUM (name eu_region, members [NORTH, SOUTH]);\n",
    "models/sales/orders.sql": (
        'MODEL (\n  description "Orders",\n  enums (\n    _state [OPEN, CLOSED],\n  ),\n);\n\n'
        "SELECT\n  order_id,\n  @sales_label('1') AS label,\n"
        '  @const("sales_cap") AS cap,\n  @enum("_state").OPEN AS state,\n'
        '  @enum("order_status").PLACED AS status\nFROM __source("raw_orders")\n'
    ),
    "models/sales/eu/eu_orders.sql": (
        'MODEL (\n  description "EU orders",\n);\n\n'
        "SELECT\n  order_id,\n  @eu_rate('2') AS rate,\n"
        "  @enum(\"eu_region\").NORTH AS region,\n  @cents('3') AS cents,\n"
        "  @sales_label('4') AS label,\n  @const(\"sales_cap\") AS cap\n"
        'FROM __ref("orders")\n'
    ),
    "models/other/customers.sql": (
        'MODEL (\n  description "Customers",\n);\n\n'
        "SELECT 1 AS customer_id, @enum(\"order_status\").SHIPPED AS status, @cents('5') AS cents\n"
    ),
    "tests/unit/test_orders.sql": (
        'TEST (name "orders_label");\n\nWITH\n'
        "__source__raw_orders AS (\n  SELECT 1 AS order_id\n),\n"
        "__expected__orders AS (\n"
        "  SELECT 1 AS order_id, @sales_label('1') AS label, @const(\"sales_cap\") AS cap\n)\n"
        "SELECT 1\n"
    ),
    "tests/unit/test_eu.sql": (
        'TEST (name "eu_rate");\n\nWITH\n__ref__orders AS (\n  SELECT 1 AS order_id\n),\n'
        "__expected__eu_orders AS (\n"
        "  SELECT 1 AS order_id, @eu_rate('2') AS rate, @enum(\"eu_region\").NORTH AS region\n)\n"
        "SELECT 1\n"
    ),
    "tests/unit/test_label_macro.sql": (
        'TEST (mode macro, name "labels_sales");\n\nWITH\n'
        "__macro_actual__ AS (\n  SELECT @sales_label('1') AS label\n),\n"
        "__macro_expected__ AS (\n  SELECT 'sales:' || 1 AS label\n)\nSELECT 1\n"
    ),
    "tests/scenarios/eu_flow.sql": (
        'SCENARIO (\n  description "EU flow"\n);\n\nWITH\n'
        "__ref__orders AS (\n  SELECT 1 AS order_id\n),\n"
        "__expected__eu_orders AS (\n"
        '  SELECT 1 AS order_id, @enum("eu_region").SOUTH AS region\n)\n'
        "SELECT 1\n"
    ),
}


@dataclass(frozen=True)
class ScopeOutcome:
    """What building the declaration scope produced under one engine."""

    kind: str
    value: tuple[object, ...]
    grants: int = 0
    error: str = ""


_FOLDERS: tuple[str, ...] = (
    "models/sales",
    "models/sales/eu",
    "models/sales/eu/north",
    "models/other",
    "models/other/archive",
)
_PLACEMENTS: tuple[str, ...] = (
    "{kind}s/f{index}",
    "{folder}/{kind}s/f{index}",
    "{folder}/_sqlbuild/{kind}s/f{index}",
    "{folder}/_{kind}s/f{index}",
    "{folder}/_sqlbuild/_{kind}s/f{index}",
)
_DECLARATION_KINDS: tuple[str, ...] = ("macro", "enum", "constant")


def write_project(*, project_dir: Path, files: dict[str, str]) -> None:
    """Write `files` below `project_dir`."""

    for relative_path, contents in files.items():
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")


def generated_scope_files(*, rng: random.Random) -> dict[str, str]:
    """Return a seeded project of scoped declarations, models, tests and scenarios."""

    files: dict[str, str] = {
        "sqlbuild_project.toml": PROJECT_CONFIG,
        "sources/raw.yml": RAW_SOURCES,
    }
    models: list[str] = [f"model_{index}" for index in range(rng.randint(1, 6))]
    for index, model in enumerate(models):
        private: str = rng.choice(("", "", f"  constants (\n    _limit_{index} 2,\n  ),\n"))
        files[f"{rng.choice(_FOLDERS)}/{model}.sql"] = (
            f'MODEL (\n  description "Model {index}",\n{private});\n\n'
            'SELECT order_id\nFROM __source("raw_orders")\n'
        )
    macros: list[str] = []
    for index in range(rng.randint(0, 8)):
        kind: str = rng.choice(_DECLARATION_KINDS)
        path: str = rng.choice(_PLACEMENTS).format(
            kind=kind, folder=rng.choice(_FOLDERS), index=index
        )
        declaration: tuple[str, str, tuple[str, ...]] = _DECLARATION_WRITERS[kind](
            path=path, index=index, variant=rng.randint(0, 4)
        )
        files[declaration[0]] = declaration[1]
        macros.extend(declaration[2])
    for index in range(rng.randint(0, 4)):
        files[f"tests/unit/test_{index}.sql"] = _TEST_WRITERS[
            rng.choices(_TEST_KINDS, weights=_TEST_WEIGHTS)[0]
        ](
            index=index,
            calls=_macro_calls(rng=rng, macros=macros),
            expected=rng.sample([*models, "missing_model"], k=rng.randint(1, 2)),
        )
    scenario: dict[str, str] = {
        "tests/scenarios/flow.sql": (
            'SCENARIO (\n  description "Flow"\n);\n\nWITH\n'
            "__source__raw_orders AS (\n  SELECT 1 AS order_id\n),\n"
            f"__expected__{rng.choice([*models, 'missing_model'])} AS (\n"
            "  SELECT 1 AS order_id\n)\nSELECT 1\n"
        )
    }
    files.update(rng.choice((scenario, scenario, {}, {}, {})))
    return files


def _macro_writer(*, path: str, index: int, variant: int) -> tuple[str, str, tuple[str, ...]]:
    del variant
    name: str = f"macro_{index}"
    return f"{path}.py", f"def {name}(value: str) -> str:\n    return value\n", (name,)


def _enum_writer(*, path: str, index: int, variant: int) -> tuple[str, str, tuple[str, ...]]:
    del index
    return f"{path}.sql", f"ENUM (name enum_{variant}, members [A, B]);\n", ()


def _constant_writer(*, path: str, index: int, variant: int) -> tuple[str, str, tuple[str, ...]]:
    del index
    return f"{path}.sql", f"CONSTANT (name constant_{variant}, value 1);\n", ()


_DECLARATION_WRITERS: dict[str, Callable[..., tuple[str, str, tuple[str, ...]]]] = {
    "macro": _macro_writer,
    "enum": _enum_writer,
    "constant": _constant_writer,
}


def _macro_calls(*, rng: random.Random, macros: list[str]) -> str:
    return "".join(
        f", @{name}('{position}') AS value_{position}"
        for position, name in enumerate(rng.sample(macros, k=min(len(macros), rng.randint(0, 2))))
    )


def _macro_test(*, index: int, calls: str, expected: list[str]) -> str:
    del expected
    return (
        f'TEST (mode macro, name "macro_test_{index}");\n\nWITH\n'
        f"__macro_actual__ AS (\n  SELECT 1 AS id{calls}\n),\n"
        f"__macro_expected__ AS (\n  SELECT 1 AS id{calls}\n)\nSELECT 1\n"
    )


def _broken_test(*, index: int, calls: str, expected: list[str]) -> str:
    del calls, expected
    return (
        f'TEST (name "broken_{index}");\n\nWITH\n__source__raw_orders AS (\n  SELECT 1\n),\n'
        "__expected__ AS (\n  SELECT 1\n)\nSELECT 1\n"
    )


def _expected_model_test(*, index: int, calls: str, expected: list[str]) -> str:
    blocks: str = ",\n".join(
        f"__expected__{model} AS (\n  SELECT 1 AS order_id{calls}\n)" for model in expected
    )
    return (
        f'TEST (name "test_{index}");\n\nWITH\n__source__raw_orders AS (\n'
        f"  SELECT 1 AS order_id\n),\n{blocks}\nSELECT 1\n"
    )


_TEST_KINDS: tuple[str, ...] = ("macro", "broken", "expected_model")
_TEST_WEIGHTS: tuple[int, ...] = (3, 1, 6)
_TEST_WRITERS: dict[str, Callable[..., str]] = {
    "macro": _macro_test,
    "broken": _broken_test,
    "expected_model": _expected_model_test,
}


def scope_engine_outcomes(
    *, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ScopeOutcome, ScopeOutcome, bool]:
    """Return the Python and native scope outcomes and whether the native index was built."""

    try:
        discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
        macros: dict[str, LoadedMacro] = load_project_macros(discovered.macro_files)
    except (DiscoveryError, CompileInputError) as error:
        failure: ScopeOutcome = ScopeOutcome(kind="discovery", value=(), error=str(error))
        return failure, failure, True
    syntax: SqlLexicalSyntax = DuckDbAdapter().sql_lexical_syntax
    python: ScopeOutcome = _scope_outcome(
        discovered=discovered,
        macros=macros,
        syntax=syntax,
        engine="python",
        monkeypatch=monkeypatch,
    )
    native: ScopeOutcome = _scope_outcome(
        discovered=discovered,
        macros=macros,
        syntax=syntax,
        engine="native",
        monkeypatch=monkeypatch,
    )
    built: bool = (
        open_native_scope_index(discovered_inputs=discovered, loaded_macros=macros) is not None
    )
    return python, native, built


def scope_command_indexes(
    *, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ScopeIndex, ScopeIndex]:
    """Return the offline `sqb scope` index under the Python and native engines."""

    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, "python")
    python: ScopeIndex = load_or_build_scope_index(project_dir=project_dir, no_cache=True)
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, "native")
    native: ScopeIndex = load_or_build_scope_index(project_dir=project_dir, no_cache=True)
    return python, native


def _scope_outcome(
    *,
    discovered: DiscoveredProjectInputs,
    macros: dict[str, LoadedMacro],
    syntax: SqlLexicalSyntax,
    engine: str,
    monkeypatch: pytest.MonkeyPatch,
) -> ScopeOutcome:
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine)
    try:
        scope: DeclarationScopeBuild = build_declaration_scope(
            discovered_inputs=discovered, loaded_macros=macros, sql_lexical_syntax=syntax
        )
    except CompileInputError as error:
        return ScopeOutcome(kind="error", value=(type(error.__cause__).__name__,), error=str(error))
    return ScopeOutcome(
        kind="ok",
        value=(scope.index, _lookup_shape(scope.resolver.lookup), scope.resolver.resource_specific),
        grants=len(scope.index.grants),
    )


def _lookup_shape(lookup: ScopeLookup) -> tuple[object, ...]:
    return (
        lookup.index,
        tuple(lookup.resources.items()),
        tuple(lookup.resources_by_path.items()),
        tuple(lookup.declarations.items()),
        tuple(lookup.usages_by_consumer.items()),
        tuple(lookup.usages_by_declaration.items()),
        tuple(lookup.grants_by_resource.items()),
        lookup.visibility_index.identities,
        lookup.visibility_index.global_positions,
        tuple(lookup.visibility_index.private_positions.items()),
        tuple(lookup.visibility_index.local_positions.items()),
        tuple(lookup.visibility_index.inherited_positions.items()),
    )
