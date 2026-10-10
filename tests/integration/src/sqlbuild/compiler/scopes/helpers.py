"""Scoped projects and engine-parity outcomes for the native declaration scope tests."""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, fields, replace
from itertools import chain
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile._helpers.attachment import declaration_scope
from sqlbuild.compiler.compile._helpers.attachment.declaration_scope import build_declaration_scope
from sqlbuild.compiler.compile._helpers.render.declarations import resolve_declaration_context
from sqlbuild.compiler.compile._helpers.render.macros import load_project_macros
from sqlbuild.compiler.compile._helpers.scenarios.core import (
    extract_sql_scenario_expected_model_names,
)
from sqlbuild.compiler.compile._helpers.sql_tests.core import (
    extract_sql_test_expected_model_names,
    extract_top_level_ctes_with_scanner,
)
from sqlbuild.compiler.compile._helpers.sql_tests.native import native_sql_test_ctes
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompileSqlTestCte,
    DeclarationResolutionContext,
    DeclarationScopeBuild,
    DeclarationScopeResolver,
    LoadedMacro,
)
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.discovery.exceptions import DiscoveryError
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredProjectInputs,
    EnumDeclaration,
)
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.frontier.types import CompilerEngine
from sqlbuild.compiler.scopes.classes.native_scope_index import NativeScopeIndex
from sqlbuild.compiler.scopes.main._declaration_lexical_path import declaration_lexical_path
from sqlbuild.compiler.scopes.main._declaration_visibility import declaration_visibility
from sqlbuild.compiler.scopes.main._native_expected_model_names import (
    native_expected_model_names,
)
from sqlbuild.compiler.scopes.main._open_native_scope_index import open_native_scope_index
from sqlbuild.compiler.scopes.main._resolve_scope_declaration_visibility import (
    resolve_scope_declaration_visibility,
)
from sqlbuild.compiler.scopes.main._resolve_scope_path_visibility import (
    resolve_scope_path_visibility,
)
from sqlbuild.compiler.scopes.main.load_or_build_scope_index import load_or_build_scope_index
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    DeclarationVisibility,
    ResourceIdentity,
    ScopeIndex,
    ScopeLookup,
    VisibilityRecord,
)
from sqlbuild.compiler.scopes.types import (
    DeclarationKind,
    ResourceKind,
    ScopeKind,
    VisibilityReason,
)
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from tests.integration.src.sqlbuild.compiler.helpers import mismatches

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


_BROKEN_SCENARIO_CTES: tuple[str, ...] = (
    "__expected__ AS (\n  SELECT 1\n)",
    "__expected__orders AS (\n  SELECT (1\n)",
    "__expected__orders (SELECT 1)",
)
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
    broken_scenario: dict[str, str] = {
        "tests/scenarios/flow.sql": (
            'SCENARIO (\n  description "Flow"\n);\n\nWITH\n'
            "__source__raw_orders AS (\n  SELECT 1 AS order_id\n),\n"
            f"{rng.choice(_BROKEN_SCENARIO_CTES)}\n"
        )
    }
    files.update(rng.choice((scenario, scenario, broken_scenario, {}, {}, {})))
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


def _broken_macro_test(*, index: int, calls: str, expected: list[str]) -> str:
    del expected
    return (
        f'TEST (mode macro, name "broken_macro_{index}");\n\nWITH\n'
        f"__macro_actual__ AS SELECT 1 AS id{calls}\n"
    )


def _expected_model_test(*, index: int, calls: str, expected: list[str]) -> str:
    blocks: str = ",\n".join(
        f"__expected__{model} AS (\n  SELECT 1 AS order_id{calls}\n)" for model in expected
    )
    return (
        f'TEST (name "test_{index}");\n\nWITH\n__source__raw_orders AS (\n'
        f"  SELECT 1 AS order_id\n),\n{blocks}\nSELECT 1\n"
    )


_TEST_KINDS: tuple[str, ...] = ("macro", "broken", "broken_macro", "expected_model")
_TEST_WEIGHTS: tuple[int, ...] = (3, 1, 1, 6)
_TEST_WRITERS: dict[str, Callable[..., str]] = {
    "macro": _macro_test,
    "broken": _broken_test,
    "broken_macro": _broken_macro_test,
    "expected_model": _expected_model_test,
}


def scope_engine_outcomes(
    *, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ScopeOutcome, ScopeOutcome, bool]:
    """Return the shipped and preview scope outcomes and whether the native index was built."""

    try:
        discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
        macros: dict[str, LoadedMacro] = load_project_macros(discovered.macro_files)
    except (DiscoveryError, CompileInputError) as error:
        failure: ScopeOutcome = ScopeOutcome(kind="discovery", value=(), error=str(error))
        return failure, failure, True
    syntax: SqlLexicalSyntax = DuckDbAdapter().sql_lexical_syntax
    shipped: ScopeOutcome = _scope_outcome(
        discovered=discovered,
        macros=macros,
        syntax=syntax,
        engine=CompilerEngine.NATIVE.value,
        monkeypatch=monkeypatch,
    )
    native: ScopeOutcome = _scope_outcome(
        discovered=discovered,
        macros=macros,
        syntax=syntax,
        engine=CompilerEngine.NATIVE_PREVIEW.value,
        monkeypatch=monkeypatch,
    )
    _ = open_native_scope_index(discovered_inputs=discovered, loaded_macros=macros)
    return shipped, native, True


def scope_command_indexes(
    *, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ScopeIndex, ScopeIndex]:
    """Return the offline `sqb scope` index under the shipped and preview engines."""

    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, CompilerEngine.NATIVE.value)
    shipped: ScopeIndex = load_or_build_scope_index(project_dir=project_dir, no_cache=True)
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, CompilerEngine.NATIVE_PREVIEW.value)
    native: ScopeIndex = load_or_build_scope_index(project_dir=project_dir, no_cache=True)
    return shipped, native


def native_scope_attempts(
    *, project_dir: Path, engine: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, ScopeOutcome]:
    """Build the declaration scope under `engine`; count how often the native index was opened."""

    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    macros: dict[str, LoadedMacro] = load_project_macros(discovered.macro_files)
    attempts: list[None] = []

    def counted(
        *, discovered_inputs: DiscoveredProjectInputs, loaded_macros: Mapping[str, LoadedMacro]
    ) -> NativeScopeIndex:
        attempts.append(None)
        return open_native_scope_index(
            discovered_inputs=discovered_inputs, loaded_macros=loaded_macros
        )

    monkeypatch.setattr(declaration_scope, "open_native_scope_index", counted)
    outcome: ScopeOutcome = _scope_outcome(
        discovered=discovered,
        macros=macros,
        syntax=DuckDbAdapter().sql_lexical_syntax,
        engine=engine,
        monkeypatch=monkeypatch,
    )
    return len(attempts), outcome


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


_TEST_LABEL: str = "tests/unit/test.sql"
_SCENARIO_LABEL: str = "tests/scenarios/orders.sql"
_LEADING: tuple[str, ...] = (
    "",
    "-- header\n",
    "/* note ) */ ",
    "# hash comment\n",
    "// slash comment\n",
    "/* outer /* inner */ ) */ ",
    "\n\t ",
    "\x1c",
    "\u00a0",
    "'quoted' ",
)
_WITH: tuple[str, ...] = (
    "WITH ",
    "with\n",
    "WITH RECURSIVE ",
    "With/*c*/",
    "w\u0131th ",
    "WITHIN ",
)
_CTE_NAMES: tuple[str, ...] = (
    "__expected__orders",
    "__expected__customers",
    "__source__raw_orders",
    "__ref__stg_orders",
    "__assert__totals",
    "__expected__",
    "__expected__caf\u00e9",
    '"__expected__quoted"',
    "helper",
)
_COLUMN_LISTS: tuple[str, ...] = ("", " (order_id, amount)", "(x)")
_AS: tuple[str, ...] = (" AS ", " as\n", "AS", " ")
_BODIES: tuple[str, ...] = (
    "(SELECT 1 AS order_id)",
    "(SELECT ')' AS x, '(' AS y)",
    "(SELECT 'it\\')' AS x)",
    "(SELECT $$ ) $$ AS x)",
    "(SELECT $tag$ ( $tag$ AS x)",
    "(SELECT '''a ) b''' AS x)",
    "(SELECT r'\\' AS x) ",
    "(SELECT E'\\')' AS x)",
    "(SELECT 1 -- )\n)",
    "(SELECT 1 # )\n)",
    '(SELECT "caf\u00e9" FROM t)',
    "(SELECT (1)",
)
_TRAILING: tuple[str, ...] = (
    "",
    "\nSELECT 1\n",
    " select 1 ;",
    " SELECT 1; -- done\n",
    " SELECT 2",
    " SELECT 1 /* open",
    "\u00a0SELECT 1",
    " $x",
    " ; ",
)
LEXICAL_SYNTAXES: dict[str, SqlLexicalSyntax] = {
    "generic": SqlLexicalSyntax(),
    "backslash_triple_raw": SqlLexicalSyntax(
        backslash_escape_quotes=frozenset({"'", '"'}),
        raw_string_prefix=True,
        triple_quoted_strings=True,
        line_comment_prefixes=frozenset({"--", "#"}),
    ),
    "escape_prefix": SqlLexicalSyntax(escape_string_prefix=True),
    "nested_comments": SqlLexicalSyntax(nested_block_comments=True),
    "slash_comments": SqlLexicalSyntax(line_comment_prefixes=frozenset({"--", "//"})),
}


@dataclass(frozen=True)
class ExpectedNameScanParity:
    """How the native relationship scans compared with Python over one corpus."""

    mismatches: list[tuple[object, object, object]]
    scanned: int
    python_errors: int
    native_errors: int


def generated_expected_model_sqls(*, rng: random.Random, count: int) -> list[str]:
    """Return seeded SQL test bodies mixing valid, dialect-sensitive and invalid CTE layouts."""

    return [_generated_expected_model_sql(rng=rng) for _ in range(count)]


def _generated_expected_model_sql(*, rng: random.Random) -> str:
    ctes: list[str] = [
        f"{rng.choice(_CTE_NAMES)}{rng.choice(_COLUMN_LISTS)}{rng.choice(_AS)}{rng.choice(_BODIES)}"
        for _ in range(rng.randint(1, 4))
    ]
    return f"{rng.choice(_LEADING)}{rng.choice(_WITH)}{','.join(ctes)}{rng.choice(_TRAILING)}"


def expected_name_scan_parity(
    *, sqls: list[str], syntax: SqlLexicalSyntax
) -> ExpectedNameScanParity:
    """Compare each native scan, test and scenario names and test CTEs, with Python's result."""

    test_texts: list[tuple[str, str]] = [(sql, _TEST_LABEL) for sql in sqls]
    scenario_texts: list[tuple[str, str]] = [(sql, _SCENARIO_LABEL) for sql in sqls]
    native: list[object] = [
        *native_expected_model_names(texts=test_texts, scenario=False, syntax=syntax),
        *native_expected_model_names(texts=scenario_texts, scenario=True, syntax=syntax),
        *native_sql_test_ctes(texts=test_texts, syntax=syntax),
    ]
    python: list[object] = [
        *(_python_expected_names(sql=sql, syntax=syntax) for sql in sqls),
        *(_python_scenario_names(sql=sql, syntax=syntax) for sql in sqls),
        *(_python_test_ctes(sql=sql, syntax=syntax) for sql in sqls),
    ]
    return ExpectedNameScanParity(
        mismatches=mismatches(inputs=[*sqls, *sqls, *sqls], expected=python, actual=native),
        scanned=sum(isinstance(outcome, tuple) for outcome in native),
        python_errors=sum(isinstance(outcome, str) for outcome in python),
        native_errors=sum(isinstance(outcome, str) for outcome in native),
    )


def _python_expected_names(*, sql: str, syntax: SqlLexicalSyntax) -> tuple[str, ...] | str:
    try:
        return extract_sql_test_expected_model_names(
            sql=sql, file_label=_TEST_LABEL, syntax=syntax, mode=SqlTestMode.MODEL
        )
    except CompileInputError as error:
        return str(error)


def _python_scenario_names(*, sql: str, syntax: SqlLexicalSyntax) -> tuple[str, ...] | str:
    try:
        return extract_sql_scenario_expected_model_names(
            sql=sql, file_label=_SCENARIO_LABEL, syntax=syntax
        )
    except CompileInputError as error:
        return str(error)


def _python_test_ctes(*, sql: str, syntax: SqlLexicalSyntax) -> tuple[tuple[str, str], ...] | str:
    try:
        ctes: tuple[CompileSqlTestCte, ...] = extract_top_level_ctes_with_scanner(
            sql=sql,
            file_label=_TEST_LABEL,
            context_label="SQL test",
            with_requirement="mock CTEs and one __expected__<model> CTE",
            cte_type=CompileSqlTestCte,
            syntax=syntax,
        )
    except CompileInputError as error:
        return str(error)
    return tuple((cte.name, cte.sql_body) for cte in ctes)


@dataclass(frozen=True)
class ContextParity:
    """Native and Python declaration contexts for every consumer of some projects."""

    targets: tuple[str, ...] = ()
    native: tuple[object, ...] = ()
    python: tuple[object, ...] = ()
    native_contexts: int = 0
    granted_contexts: int = 0
    private_contexts: int = 0
    python_only_paths: int = 0


_CONTEXT_DICT_FIELDS: tuple[str, ...] = tuple(
    item.name for item in fields(DeclarationResolutionContext) if item.name != "consumer"
)


def declaration_context_parity(
    *, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> ContextParity:
    """Resolve every resource, resource path and declaration file natively and in Python."""

    try:
        discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
        macros: dict[str, LoadedMacro] = load_project_macros(discovered.macro_files)
        monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, CompilerEngine.NATIVE_PREVIEW.value)
        scope: DeclarationScopeBuild = build_declaration_scope(
            discovered_inputs=discovered,
            loaded_macros=macros,
            sql_lexical_syntax=DuckDbAdapter().sql_lexical_syntax,
        )
    except (DiscoveryError, CompileInputError):
        return ContextParity()
    resolver: DeclarationScopeResolver = scope.resolver
    targets: list[tuple[Path, ResourceIdentity | None]] = [
        *(
            (Path(records[0].path), identity)
            for identity, records in resolver.lookup.resources.items()
        ),
        *((Path(path), None) for path in resolver.lookup.resources_by_path),
        *((Path(record.path), None) for record in scope.index.declarations),
    ]
    native: list[DeclarationResolutionContext] = [
        resolve_declaration_context(
            resolver=replace(resolver, contexts_by_directory={}),
            file_path=file_path,
            resource=resource,
        )
        for file_path, resource in targets
    ]
    python: list[DeclarationResolutionContext] = [
        _python_declaration_context(resolver=resolver, file_path=file_path, resource=resource)
        for file_path, resource in targets
    ]
    indexed: list[bool] = [
        bool(resource) or file_path.as_posix() in resolver.lookup.resources_by_path
        for file_path, resource in targets
    ]
    records: list[list[VisibilityRecord]] = list(map(_visibility_records, native))
    return ContextParity(
        targets=tuple(
            f"{project_dir.name}:{file_path}:{resource}" for file_path, resource in targets
        ),
        native=tuple(map(_context_shape, native)),
        python=tuple(map(_context_shape, python)),
        native_contexts=sum(indexed),
        granted_contexts=sum(map(_has_grant, records)),
        private_contexts=sum(map(_has_private_value, records)),
        python_only_paths=len(indexed) - sum(indexed),
    )


def combined_context_parity(parities: list[ContextParity]) -> ContextParity:
    """Concatenate the compared contexts and add up the coverage counts of several projects."""

    return ContextParity(
        targets=tuple(chain.from_iterable(parity.targets for parity in parities)),
        native=tuple(chain.from_iterable(parity.native for parity in parities)),
        python=tuple(chain.from_iterable(parity.python for parity in parities)),
        native_contexts=sum(parity.native_contexts for parity in parities),
        granted_contexts=sum(parity.granted_contexts for parity in parities),
        private_contexts=sum(parity.private_contexts for parity in parities),
        python_only_paths=sum(parity.python_only_paths for parity in parities),
    )


def _has_grant(records: list[VisibilityRecord]) -> bool:
    return any(record.through is not None for record in records)


def _has_private_value(records: list[VisibilityRecord]) -> bool:
    return any(record.reason is VisibilityReason.PRIVATE_OWNER for record in records)


def _visibility_records(context: DeclarationResolutionContext) -> list[VisibilityRecord]:
    return list(
        chain.from_iterable(
            chain(
                context.enum_visibility.values(),
                context.constant_visibility.values(),
                context.macro_visibility.values(),
            )
        )
    )


def _context_shape(context: DeclarationResolutionContext) -> tuple[object, ...]:
    return (
        *(tuple(getattr(context, name).items()) for name in _CONTEXT_DICT_FIELDS),
        context.consumer,
    )


def _python_declaration_context(
    *, resolver: DeclarationScopeResolver, file_path: Path, resource: ResourceIdentity | None
) -> DeclarationResolutionContext:
    """The context the deleted Python projection built from the scope library's resolution."""

    resolution: DeclarationVisibility = resolve_scope_declaration_visibility(
        lookup=resolver.lookup, target=resource or file_path
    )
    visible, inaccessible, visibility = {
        True: _path_visibility,
        False: _resource_visibility,
    }[resolution.target.unknown](resolver=resolver, resolution=resolution, target_path=file_path)
    values: Mapping[DeclarationIdentity, object] = resolver.projection.declarations
    macro_records: tuple[DeclarationRecord, ...] = _valued(visible, values, LoadedMacro)
    return DeclarationResolutionContext(
        enums=_values_by_name(visible, values, EnumDeclaration),
        constants=_values_by_name(visible, values, ConstantDeclaration),
        inaccessible_enums=_by_name(inaccessible, DeclarationKind.ENUM),
        inaccessible_constants=_by_name(inaccessible, DeclarationKind.CONSTANT),
        enum_visibility=_visibility_by_name(visible, visibility, DeclarationKind.ENUM),
        constant_visibility=_visibility_by_name(visible, visibility, DeclarationKind.CONSTANT),
        macros=_values_by_name(visible, values, LoadedMacro),
        macro_records={record.identity.name: record for record in macro_records},
        macro_visibility=_visibility_by_name(visible, visibility, DeclarationKind.MACRO),
        inaccessible_macros=_by_name(inaccessible, DeclarationKind.MACRO),
        consumer=resource or next((match.identity for match in resolution.target.matches), None),
    )


def _valued(
    records: tuple[DeclarationRecord, ...],
    values: Mapping[DeclarationIdentity, object],
    value_type: type,
) -> tuple[DeclarationRecord, ...]:
    return tuple(
        filter(lambda record: isinstance(values.get(record.identity), value_type), records)
    )


def _values_by_name[T](
    records: tuple[DeclarationRecord, ...],
    values: Mapping[DeclarationIdentity, object],
    value_type: type[T],
) -> dict[str, T]:
    return {
        record.identity.name: cast(T, values[record.identity])
        for record in _valued(records, values, value_type)
    }


def _of_kind(
    records: tuple[DeclarationRecord, ...], kind: DeclarationKind
) -> tuple[DeclarationRecord, ...]:
    return tuple(filter(lambda record: record.identity.kind is kind, records))


def _by_name(
    records: tuple[DeclarationRecord, ...], kind: DeclarationKind
) -> dict[str, DeclarationRecord]:
    return {record.identity.name: record for record in _of_kind(records, kind)}


def _visibility_by_name(
    records: tuple[DeclarationRecord, ...],
    visibility: dict[DeclarationIdentity, list[VisibilityRecord]],
    kind: DeclarationKind,
) -> dict[str, tuple[VisibilityRecord, ...]]:
    return {
        record.identity.name: tuple(visibility.get(record.identity, ()))
        for record in _of_kind(records, kind)
    }


type _Visibility = tuple[
    tuple[DeclarationRecord, ...],
    tuple[DeclarationRecord, ...],
    dict[DeclarationIdentity, list[VisibilityRecord]],
]


def _resource_visibility(
    *, resolver: DeclarationScopeResolver, resolution: DeclarationVisibility, target_path: Path
) -> _Visibility:
    _ = target_path
    visibility: defaultdict[DeclarationIdentity, list[VisibilityRecord]] = defaultdict(list)
    for record in resolution.visible:
        visibility[record.declaration].append(record)
    return (
        tuple(resolver.lookup.declarations[item.declaration][0] for item in resolution.visible),
        tuple(resolver.lookup.declarations[identity][0] for identity in resolution.inaccessible),
        dict(visibility),
    )


def _path_visibility(
    *, resolver: DeclarationScopeResolver, resolution: DeclarationVisibility, target_path: Path
) -> _Visibility:
    _ = resolution
    lexical_path: Path = next(
        map(
            lambda record: Path(declaration_lexical_path(record=record)),
            filter(
                lambda record: (
                    record.path == target_path.as_posix() and record.scope is not ScopeKind.PRIVATE
                ),
                resolver.lookup.index.declarations,
            ),
        ),
        target_path,
    )
    visible, inaccessible = resolve_scope_path_visibility(lookup=resolver.lookup, path=lexical_path)
    path_resource: ResourceIdentity = ResourceIdentity(
        ResourceKind.MODEL, f"<path:{lexical_path.as_posix()}>"
    )
    reasons: Iterator[tuple[DeclarationRecord, VisibilityReason | None]] = (
        (record, declaration_visibility(declaration=record, consumer=lexical_path))
        for record in visible
    )
    return (
        visible,
        inaccessible,
        {
            record.identity: [
                VisibilityRecord(path_resource, record.identity, cast(VisibilityReason, reason))
            ]
            for record, reason in filter(lambda pair: pair[1] is not None, reasons)
        },
    )
