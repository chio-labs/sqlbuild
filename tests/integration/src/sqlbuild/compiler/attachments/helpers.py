"""Generated authored SQL and attached audits for the native attachment parity tests."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import cast

import pytest

import sqlbuild._native as _native
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.attachments.main._render_native_attached_audit import (
    render_native_attached_audit,
)
from sqlbuild.compiler.attachments.models import NativeAuditPolicies, NativeRenderedAudit
from sqlbuild.compiler.auditing.types import AuditRunScope, AuditSeverity
from sqlbuild.compiler.compile._helpers.attachment.audits import (
    merge_audit_arguments,
    render_generic_audit_sql,
    resolve_audit_run_scope,
    resolve_audit_severity,
)
from sqlbuild.compiler.compile._helpers.attachment.functions import build_sql_function_inputs
from sqlbuild.compiler.compile._helpers.attachment.sql_tests import (
    build_test_inputs,
    validate_test_ctes,
)
from sqlbuild.compiler.compile._helpers.render import macros
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import reject_cursor_intrinsics
from sqlbuild.compiler.compile._helpers.render.parameters import expand_test_parameters
from sqlbuild.compiler.compile._helpers.render.sql_vars import expand_authored_sql_result
from sqlbuild.compiler.compile._helpers.scenarios.core import extract_sql_scenario_ctes
from sqlbuild.compiler.compile._helpers.sql_tests.core import (
    complete_omitted_ceremonial_select,
    extract_sql_test_ctes,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import (
    AuthoredSqlExpansionResult,
    CompileAdapterContext,
    CompileModelSqlTestCtes,
    CompileProjectInputs,
    CompileSqlTestCtes,
    DeclarationExpansionContext,
    DeclarationResolutionContext,
    LoadedMacro,
    MacroContext,
)
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredPythonFunctionFile,
    DiscoveredSqlFunctionFile,
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestFile,
)
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.frontier.main._compile_frontier import compile_frontier
from sqlbuild.compiler.frontier.types import CompilerEngine, CompilerStage
from sqlbuild.compiler.planner.constants import (
    MICROBATCH_END_SENTINEL,
    MICROBATCH_START_SENTINEL,
)
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.spec.contracts.main.resolve_effective_collection_rendering import (
    resolve_effective_collection_rendering,
)
from sqlbuild.spec.contracts.models import (
    DefaultsConfig,
    LocalConfig,
    ProjectConfig,
    SettingsConfig,
    TargetConfig,
)
from sqlbuild.sql_values.main.normalize import normalize_sql_value
from sqlbuild.sql_values.models import SqlValue
from sqlbuild.sql_values.types import CollectionRendering
from tests.integration.src.sqlbuild.compiler.attachments._test_types import (
    FunctionHeaderParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.model_loop.helpers import (
    DECLARATIONS,
    generated_reference_sql,
)

EFFECTIVE_VARS: dict[str, object] = {
    "region": "north",
    "limit_rows": 10,
    "ratio": 0.5,
    "enabled": True,
    "unset": None,
    "regions": ["north", "south"],
}
_VARIABLE_TOKENS: tuple[str, ...] = (
    "@@region",
    "@@limit_rows ",
    "'@@region'",
    "@@ratio",
    "@@enabled",
    "@@unset",
    "@@@window_start",
    "@@ENV:SQB_ORDERS_REGION",
    "@@ENV:SQB_MISSING_REGION",
    "@@regions",
    "@@missing",
    "@@CTX:run.target",
    "-- @@missing\n",
)
_MACRO_CONTEXT: MacroContext = MacroContext(
    adapter_name="duckdb", sql_analysis_enabled=True, target_name="dev"
)


def generated_authored_sql(*, rng: random.Random) -> str:
    """Return SQL mixing project variables with enum and constant references."""

    parts: list[str] = [
        generated_reference_sql(rng=rng),
        *rng.choices(_VARIABLE_TOKENS, k=rng.randint(0, 3)),
    ]
    rng.shuffle(parts)
    return " ".join(parts)


_DOLLAR_PIECES: tuple[str, ...] = (
    "$",
    "$$",
    "$t$",
    "$tag$",
    "a$",
    "$1",
    "$1$",
    "--",
    "/*",
    "*/",
    "'",
    "\n",
    " ",
    "@@region",
    "@@limit_rows",
    "@@missing",
    "@@ENV:SQB_ORDERS_REGION",
    '@const("sales_cap")',
    '@enum("order_status").PLACED',
)


def generated_dollar_authored_sql(*, rng: random.Random) -> str:
    """Return SQL dense in dollar quotes around variables, enum and constant references."""

    parts: list[str] = [
        generated_reference_sql(rng=rng),
        *rng.choices(_DOLLAR_PIECES, k=rng.randint(1, 10)),
    ]
    rng.shuffle(parts)
    return "".join(parts)


def authored_outcome(
    *, sql: str, engine: CompilerEngine, monkeypatch: pytest.MonkeyPatch
) -> AuthoredSqlExpansionResult | str:
    """Expand one string under `engine`, returning the result or Python's error text."""

    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine.value)
    monkeypatch.setenv("SQB_ORDERS_REGION", "south")
    try:
        return expand_authored_sql_result(
            sql=sql,
            file_path=Path("audits/orders.sql"),
            effective_vars=EFFECTIVE_VARS,
            loaded_macros={},
            macro_context=_MACRO_CONTEXT,
            value_renderer=DuckDbAdapter(),
            collection_rendering=CollectionRendering.VALUE_LIST,
            declarations=DECLARATIONS,
        )
    except CompileInputError as error:
        return str(error)


_SQL_PIECES: tuple[str, ...] = (
    "SELECT * FROM t WHERE ",
    "@column",
    "@'column'",
    "@values",
    "@'values'",
    "@limit_rows",
    "@@column",
    "@@@window",
    "@tidy(@column)",
    "@column (x)",
    " AND ",
    "'@column'",
    "@column\u00e9",
    "@column\u00a0(",
    "\n",
)
_VALUES: tuple[object, ...] = (
    "status",
    "it's",
    1,
    1.0,
    -0.0,
    True,
    None,
    ["placed", 2, None],
    ("placed",),
    {"nested": 1},
    float("nan"),
    AuditSeverity.WARN,
    10**20,
)
_SEVERITIES: tuple[str | None, ...] = (None, None, None, "warn", "error", AuditSeverity.WARN)
_RUN_SCOPES: tuple[str | None, ...] = (None, None, None, "final", "delta_and_final")
_RARE: tuple[tuple[str, object], ...] = (
    ("sql", "@missing"),
    ("severity", "fatal"),
    ("severity", ""),
    ("run_scope", "delta"),
    ("column", "amount"),
    ("column", 1),
)


@dataclass(frozen=True)
class GeneratedAudit:
    """One attachment: SQL, arguments and authored policies."""

    sql_body: str
    evidence_sql: str
    implicit_arguments: dict[str, object]
    explicit_arguments: dict[str, object]
    instance_severity: str | None
    default_severity: str | None
    instance_run_scope: str | None
    default_run_scope: str | None


@dataclass(frozen=True)
class AuditParity:
    """Python's rendering (or error text) and the native rendering (or None)."""

    audit: GeneratedAudit
    python: tuple[object, ...] | str
    native: NativeRenderedAudit | None


def generated_audit(*, rng: random.Random) -> GeneratedAudit:
    """Return one attachment mixing parameter shapes, argument values and policies."""

    rare: dict[str, object] = dict(rng.choices(_RARE, k=int(rng.random() < 0.3)))
    explicit: dict[str, object] = {
        "values": rng.choice(_VALUES),
        "limit_rows": rng.choice(_VALUES),
    }
    explicit.update(filter(_is_column_override, rare.items()))
    return GeneratedAudit(
        sql_body="".join(rng.choices(_SQL_PIECES, k=rng.randint(1, 8))) + str(rare.get("sql", "")),
        evidence_sql="SELECT @column FROM t",
        implicit_arguments={"column": rng.choice(("status", "amount"))},
        explicit_arguments=explicit,
        instance_severity=cast(str | None, rare.get("severity", rng.choice(_SEVERITIES))),
        default_severity=rng.choice(_SEVERITIES),
        instance_run_scope=cast(str | None, rare.get("run_scope", rng.choice(_RUN_SCOPES))),
        default_run_scope=rng.choice(_RUN_SCOPES),
    )


def _is_column_override(item: tuple[str, object]) -> bool:
    return item[0] == "column"


def audit_parity(audit: GeneratedAudit) -> AuditParity:
    """Render one attachment with Python's helpers and natively."""

    return AuditParity(
        audit=audit,
        python=_python_rendering(audit),
        native=render_native_attached_audit(
            sql_body=audit.sql_body,
            evidence_sql=audit.evidence_sql,
            implicit_arguments=audit.implicit_arguments,
            explicit_arguments=audit.explicit_arguments,
            policies=NativeAuditPolicies(
                measurement=False,
                has_thresholds=False,
                has_minimum_samples=False,
                threshold_error=False,
                instance_severity=audit.instance_severity,
                default_severity=audit.default_severity,
                instance_run_scope=audit.instance_run_scope,
                default_run_scope=audit.default_run_scope,
            ),
        ),
    )


def is_native(parity: AuditParity) -> bool:
    """Whether the native rendering answered instead of deferring to Python."""

    return parity.native is not None


def native_outcome(parity: AuditParity) -> tuple[object, ...]:
    """The native rendering spelled like Python's, with the run scope value it selects."""

    rendered: NativeRenderedAudit = cast(NativeRenderedAudit, parity.native)
    run_scope: str | None = {
        "instance": parity.audit.instance_run_scope,
        "default": parity.audit.default_run_scope,
    }.get(rendered.run_scope_source, AuditRunScope.DELTA_AND_FINAL)
    return (rendered.sql_body, rendered.evidence_sql, AuditSeverity(rendered.severity), run_scope)


def _python_rendering(audit: GeneratedAudit) -> tuple[object, ...] | str:
    owner: Path = Path("models/orders.sql")
    try:
        merged: dict[str, object] = merge_audit_arguments(
            owner_file=owner,
            definition_name="floor",
            implicit_arguments=audit.implicit_arguments,
            explicit_arguments=audit.explicit_arguments,
        )
        rendered: tuple[str, ...] = tuple(
            render_generic_audit_sql(
                sql=sql, arguments=merged, owner_file=owner, definition_name="floor"
            )
            for sql in (audit.sql_body, audit.evidence_sql)
        )
        severity: AuditSeverity = resolve_audit_severity(
            instance_severity=audit.instance_severity,
            default_severity=audit.default_severity,
            audit_label="floor",
        )
        run_scope: str = resolve_audit_run_scope(
            instance_run_scope=audit.instance_run_scope,
            default_run_scope=audit.default_run_scope,
        )
    except CompileInputError as error:
        return str(error)
    return (*rendered, severity, run_scope)


NATIVE_ATTACHMENT_ENTRIES: tuple[str, ...] = (
    "scan_test_parameter_references",
    "omitted_ceremonial_select",
    "extract_sql_scenario_json",
    "SqlTestTargetCatalog",
    "pair_seed_files",
    "render_attached_generic_audit",
    "expand_config_templates",
    "substitute_static_project_vars",
    "scan_sql_declaration_references",
)
_MISSING_ENV: str = "SQB_ATTACHMENTS_UNSET"
ATTACHMENT_PROJECT: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "orders"\nadapter = "duckdb"\ndefault_target = "dev"\n\n'
        '[vars]\nregion = "north"\n\n'
        '[connections.local]\ndatabase = "orders.duckdb"\n\n'
        '[targets.dev]\nconnection = "local"\nschema = "dev"\n'
    ),
    "macros/labels.py": (
        "def tidy_label(expression: str) -> str:\n"
        '    """Trim and lower-case a label."""\n'
        '    return f"LOWER(TRIM({expression}))"\n'
    ),
    "seeds/channel_codes.csv": "id,label\n1,web\n2,store\n",
    "seeds/channel_codes.yml": (
        "seeds:\n  - name: channel_codes\n    description: Channel codes.\n    columns:\n"
        "      - name: id\n        type: INTEGER\n        audits:\n          - not_null\n"
        "      - name: label\n        type: VARCHAR\n"
    ),
    "seeds/product_codes.csv": "id\n1\n",
    "seeds/product_codes.yml": (
        "seeds:\n  - name: product_codes\n    columns:\n      - name: id\n        type: INTEGER\n"
    ),
    "sources/events.yml": (
        "sources:\n  - name: order_events\n"
        f"    description: \"Order feed ${{coalesce(ENV:{_MISSING_ENV}, 'events')}}\"\n"
        "    expression: \"(SELECT 1 AS id, @tidy_label('@@region') AS region, "
        '$$--@@region /* $$ AS note)"\n'
        "    columns:\n      - name: id\n        type: INTEGER\n        audits:\n"
        "          - accepted_values:\n              values: [1, 2]\n"
        "      - name: region\n        type: VARCHAR\n"
    ),
    "functions/sql/order_label.sql": (
        'FUNCTION (\n  description "Label an order status.",\n'
        f"  schema \"${{coalesce(ENV:{_MISSING_ENV}, 'udfs')}}\",\n"
        "  arguments (raw_status STRING),\n  returns STRING,\n);\n\n"
        'UPPER(@tidy_label("raw_status"))\n'
    ),
    "audits/generic/amount_floor.sql": (
        'AUDIT ();\n\nSELECT *\nFROM __ref("@model")\nWHERE @column < @minimum '
        "AND @tidy_label(\"label\") <> @'label' AND $tag$--@@region$tag$ <> @'label'\n"
    ),
    "models/orders.sql": (
        'MODEL (\n  materialized table,\n  description "Orders.",\n'
        '  audits [amount_floor (column amount, minimum -5, label "it\'s", severity warn)],\n'
        ");\n\nSELECT c.id, 1.5 AS amount, c.label\n"
        'FROM __seed("channel_codes") c\nJOIN __source("order_events") e ON e.id = c.id\n'
    ),
    "tests/unit/test_orders.sql": (
        "TEST();\n\nWITH\n__seed__channel_codes AS (\n"
        "  SELECT 1 AS id, @tidy_label(\"' Web '\") AS label, $$ /* $$ AS note, "
        "'@@region' AS region -- */\n),\n"
        "__source__order_events AS (\n  SELECT 1 AS id, 'north' AS region\n),\n"
        "__expected__orders AS (\n  SELECT 1 AS id, 1.5 AS amount, 'web' AS label\n)\n"
        "SELECT 1\n"
    ),
    "tests/unit/test_orders_cases.sql": (
        'TEST (\n  name "orders_keep_region",\n  parameters (\n    region_value string,\n  ),\n'
        '  cases (\n    north (region_value "north"),\n'
        '    quoted (region_value "it\'s"),\n  ),\n);\n\n'
        "WITH\n__seed__channel_codes AS (SELECT 1 AS id, 'web' AS label),\n"
        '__source__order_events AS (SELECT 1 AS id, @param("region_value") AS region),\n'
        "__expected__orders AS (SELECT 1 AS id, 1.5 AS amount, 'web' AS label);\n"
    ),
    "tests/unit/test_tidy_label.sql": (
        'TEST (mode macro, name "tidies_labels");\n\n'
        "WITH\ninput_values AS (SELECT ' Web ' AS label),\n"
        '__macro_actual__ AS (SELECT @tidy_label("label") AS label FROM input_values),\n'
        "__macro_expected__ AS (SELECT 'web' AS label)\nSELECT 1\n"
    ),
    "tests/scenarios/orders_scenario.sql": (
        'SCENARIO (\n  description "Orders join their channel"\n);\n\n'
        "WITH\n__seed__channel_codes AS (\n  SELECT 1 AS id, @tidy_label(\"'Web'\") AS label\n),\n"
        "__source__order_events AS (\n  SELECT 1 AS id, 'north' AS region\n),\n"
        "__expected__orders AS (\n  SELECT 1 AS id, 1.5 AS amount, 'web' AS label\n)\n"
        "SELECT 1\n"
    ),
}


def attachment_engine_outcome(
    *,
    project_dir: Path,
    engine: CompilerEngine,
    overrides: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[frozenset[str], str]:
    """Build compile inputs under `engine`; return the native entries called and the outcome."""

    for relative_path, contents in {**ATTACHMENT_PROJECT, **overrides}.items():
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    called: set[str] = set()
    for name in NATIVE_ATTACHMENT_ENTRIES:
        monkeypatch.setattr(_native, name, _recorded(called=called, name=name))
    bridged: list[Path] = []
    monkeypatch.setattr(macros, "_bridged_sql_macros", _recorded_bridge(bridged=bridged))
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine.value)
    try:
        inputs: CompileProjectInputs = compile_frontier(
            until=CompilerStage.COMPILE_PROJECT_INPUTS,
            python_stage=partial(_compile_inputs, project_dir=project_dir),
        )
    except CompileInputError as error:
        return frozenset(called), f"error: {error}".replace(str(project_dir), "<project>")
    called.update(f"bridged:{str(path).replace(str(project_dir), '<project>')}" for path in bridged)
    return frozenset(called), repr(
        (
            inputs.seed_inputs,
            inputs.source_inputs,
            inputs.sql_function_inputs,
            inputs.audit_inputs,
            inputs.test_inputs,
            inputs.scenario_inputs,
            inputs.diagnostics,
        )
    ).replace(str(project_dir), "<project>")


def _compile_inputs(*, project_dir: Path) -> CompileProjectInputs:
    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    adapter: DuckDbAdapter = DuckDbAdapter()
    return build_compile_inputs(
        discovered_inputs=discovered,
        adapter_context=CompileAdapterContext(
            value_renderer=adapter,
            collection_rendering=resolve_effective_collection_rendering(
                project_config=discovered.project_config, declaration_override=None
            ),
            python_functions_inherit_default_namespace=(
                adapter.python_functions_inherit_default_namespace()
            ),
            sql_lexical_syntax=adapter.sql_lexical_syntax,
        ),
        run_id="20261008T000000Z_orders",
        resolved_connection={},
        no_sql_validation=True,
        defer_model_sql_validation=True,
        no_cache=True,
    )


def _recorded_bridge(*, bridged: list[Path]) -> Callable[..., object]:
    entry: Callable[..., object] = cast(Callable[..., object], macros._bridged_sql_macros)

    def recorded(*, consumer_path: Path, **arguments: object) -> object:
        bridged.append(consumer_path)
        return entry(consumer_path=consumer_path, **arguments)

    return recorded


def _recorded(*, called: set[str], name: str) -> Callable[..., object]:
    entry: Callable[..., object] = getattr(_native, name)

    def recorded(*args: object) -> object:
        called.add(name)
        return entry(*args)

    return recorded


_INTRINSIC_PIECES: tuple[str, ...] = (
    "SELECT ",
    "__cursor_start",
    "__cursor_end",
    "()",
    "( )",
    "(1)",
    "x",
    "_",
    "\u00e9",
    "'",
    '"',
    "`",
    "``",
    "''",
    "$$",
    "$tag$",
    "$1",
    "--",
    "\n",
    "/*",
    "*/",
    " ",
    MICROBATCH_START_SENTINEL,
)


def generated_intrinsic_sql(*, rng: random.Random) -> str:
    """Return SQL mixing intrinsic names with quotes, comments and identifier neighbours."""

    return "".join(rng.choices(_INTRINSIC_PIECES, k=rng.randint(1, 10)))


def python_intrinsic_outcome(sql: str) -> str | None:
    """Python's rejection message, or None where Python accepts the SQL."""

    try:
        reject_cursor_intrinsics(sql=sql, context="Source expression 'orders'")
    except CompileInputError as error:
        return str(error)
    return None


def native_intrinsic_free(sql: str) -> bool:
    """Whether the native check accepts the SQL without Python."""

    return _native.sql_free_of_cursor_intrinsics(
        sql, [MICROBATCH_START_SENTINEL, MICROBATCH_END_SENTINEL]
    )


_PARAMETER_PIECES: tuple[str, ...] = (
    "SELECT ",
    '@param("region")',
    '@param ( "limit_rows" )',
    '@param(\n"region"\n)',
    '@param(\u00a0"region")',
    '@param("missing")',
    "@param(region)",
    "@params",
    "@param_x",
    "'@param(\"region\")'",
    '"quoted"',
    "`tick`",
    '$$ @param("region") $$',
    "$1",
    '-- @param("region")\n',
    '/* @param("region") */',
    "'",
    "/*",
    "\u00e9",
    ", ",
)
PARAMETER_VALUES: tuple[tuple[str, SqlValue], ...] = (
    ("region", normalize_sql_value(raw_value="north", context="region")),
    ("limit_rows", normalize_sql_value(raw_value=10, context="limit_rows")),
)


def generated_parameter_sql(*, rng: random.Random) -> str:
    """Return a test body mixing parameter references with quotes and comments."""

    return "".join(rng.choices(_PARAMETER_PIECES, k=rng.randint(1, 8)))


def parameter_outcome(
    *, sql: str, engine: CompilerEngine, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, frozenset[str]] | str:
    """Expand one body's parameters under `engine`, returning Python's error text on failure."""

    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine.value)
    try:
        return expand_test_parameters(
            sql=sql,
            file_path=Path("tests/unit/test_orders.sql"),
            values=PARAMETER_VALUES,
            value_renderer=DuckDbAdapter(),
            test_name="orders",
            case_name="north",
        )
    except CompileInputError as error:
        return str(error)


_BODY_PIECES: tuple[str, ...] = (
    "WITH ",
    "with ",
    "WITHIN ",
    "w\u0131th ",
    "__seed__orders AS (SELECT 1)",
    "a AS (SELECT ')' AS x)",
    "b AS (SELECT (1))",
    ", ",
    ")",
    "(",
    " SELECT 1",
    ";",
    "\n",
    " -- done",
    " # done",
    " /* done */",
    "/* /* nested */ */",
    "'",
    "'it\\'s'",
    "'''tri)ple'''",
    "$$)$$",
    "$1",
    "\u00e9",
    "\v",
)


def generated_test_body(*, rng: random.Random) -> str:
    """Return a test or scenario body around CTEs, terminators, comments and quotes."""

    keyword: str = rng.choice(_BODY_PIECES[:4])
    ctes: str = ", ".join(rng.choices(_BODY_PIECES[4:7], k=rng.randint(1, 3)))
    return keyword + ctes + "".join(rng.choices(_BODY_PIECES, k=rng.randint(0, 3)))


def completed_body(
    *,
    sql: str,
    syntax: SqlLexicalSyntax,
    engine: CompilerEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    """Complete one body's omitted `SELECT 1` under `engine`."""

    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine.value)
    return complete_omitted_ceremonial_select(sql=sql, syntax=syntax)


_RAW_MODE_CTES: dict[SqlTestMode, tuple[str, str]] = {
    SqlTestMode.MACRO: ("__macro_actual__", "__macro_expected__"),
    SqlTestMode.UDF: ("__udf_actual__", "__udf_expected__"),
    SqlTestMode.TABLE_FN: ("__table_fn_actual__", "__table_fn_expected__"),
}
_RAW_CALLS: tuple[str, ...] = (
    "",
    "@tidy_label(1)",
    "@MY_MACRO(1)",
    '__udf("order_label")',
    '__udf ("order_label")',
    "__udf('order_label')",
    '__udf("order_label", 1)',
    '__table_fn("order_rows")',
    "'__udf(\"order_label\")'",
    '-- __udf("order_label")\n',
    "/* @tidy_label(1) */",
    '$$__udf("order_label")$$',
    "@m()",
    "@@region",
    '__ref("orders")',
    '__source("events", "orders")',
    '__udf("\u00e9")',
    '`__udf("order_label")`',
    '__udf\u00a0("order_label")',
    '\u00e9__udf("order_label")',
)
_RAW_CTE_NAMES: tuple[str, ...] = (
    "helper",
    "a\u00e9",
    '"quoted"',
    "`ticked`",
    "a$b",
    "__ref__orders",
    "__expected__orders",
    "__macro__tidy",
    "__udf_actual__",
    "__udf_expected__",
    "__macro_expected__",
    "__table_fn_expected__",
    "HELPER",
    "\u0131",
    "\u017f",
)
_RAW_TAILS: tuple[str, ...] = ("", " FROM helper", " -- c", " UNION ALL SELECT 2", ", 'x' AS b")


def _raw_body(rng: random.Random) -> str:
    call: str = rng.choice(("1", "1", "1", "1", *_RAW_CALLS))
    projection: str = rng.choice((f"SELECT {call} AS a", f"SELECT {call} AS a", f"SELECT {call}"))
    return projection + rng.choice(("", "", "", *_RAW_TAILS))


def generated_raw_direct_logic_test(*, rng: random.Random) -> tuple[str, SqlTestMode]:
    """Return one unexpanded direct-logic test with the shapes Python and native read apart."""

    mode: SqlTestMode = rng.choice(tuple(_RAW_MODE_CTES))
    actual, expected = _RAW_MODE_CTES[mode]
    ctes: list[tuple[str, str]] = [
        (actual, _raw_body(rng)),
        (expected, _raw_body(rng)),
        *((rng.choice(_RAW_CTE_NAMES), _raw_body(rng)) for _ in range(rng.choice((0, 0, 1, 2)))),
    ]
    rng.shuffle(ctes)
    body: str = ", ".join(f"{name} AS ({sql})" for name, sql in ctes)
    return f"WITH {body}" + rng.choice(("", "", " SELECT 1", ";")), mode


def python_raw_extraction_accepts(*, sql: str, mode: SqlTestMode) -> bool:
    """Whether Python's raw direct-logic pass accepts `sql` before expansion."""

    try:
        extract_sql_test_ctes(
            sql=sql,
            file_label="tests/unit/test_logic.sql",
            syntax=DuckDbAdapter().sql_lexical_syntax,
            mode=mode,
        )
    except CompileInputError:
        return False
    return True


def raw_test_compile_outcome(
    *, sql: str, mode: SqlTestMode, engine: CompilerEngine, monkeypatch: pytest.MonkeyPatch
) -> str:
    """Build one unexpanded direct-logic test's input under `engine`, or Python's error text."""

    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine.value)
    adapter: DuckDbAdapter = DuckDbAdapter()
    try:
        return repr(
            build_test_inputs(
                discovered_inputs=DiscoveredProjectInputs(
                    project_config=ProjectConfig(name="orders", adapter="duckdb"),
                    local_config=LocalConfig(),
                    test_files=(
                        DiscoveredSqlTestFile(
                            file_path=Path("/project/tests/unit/test_logic.sql"),
                            relative_path=Path("tests/unit/test_logic.sql"),
                            contents=sql,
                            blocks=(
                                DiscoveredSqlTestBlock(
                                    test_index=0, header_values={}, sql_body=sql, mode=mode
                                ),
                            ),
                        ),
                    ),
                ),
                effective_vars={"region": "north"},
                macro_context=_MACRO_CONTEXT,
                loaded_macros={},
                declaration_expansion=DeclarationExpansionContext(
                    declarations=DeclarationResolutionContext(),
                    value_renderer=adapter,
                    collection_rendering=CollectionRendering.VALUE_LIST,
                ),
                sql_lexical_syntax=adapter.sql_lexical_syntax,
            )
        )
    except CompileInputError as error:
        return f"error: {error}"


_SCENARIO_CTES: tuple[str, ...] = (
    "__source__raw_orders AS (SELECT 1 AS id, 'placed' AS status)",
    "__ref__customers AS (SELECT 1 AS id)",
    "__seed__channel_codes AS (SELECT 1 AS id, 'web' AS label)",
    "__dbt_ref__legacy__orders AS (SELECT 1 AS id)",
    "__table_fn__order_rows AS (SELECT 1 AS id)",
    "helper AS (SELECT id FROM __source__raw_orders)",
    "__expected__orders AS (SELECT 1 AS id)",
    "__expected__orders_view AS (SELECT id FROM helper)",
    "__assert__positive AS (SELECT id FROM helper WHERE id < 0)",
    "__assert__matches AS (SELECT * FROM __expected__orders)",
    "__expected__nested AS (WITH __assert__inner AS (SELECT 1) SELECT 1 AS id)",
    "__macro__tidy AS (SELECT 'x')",
    '"__source__quoted" AS (SELECT 1)',
    "__expected__ AS (SELECT 1)",
    "__source__raw_orders AS (SELECT 2 AS id)",
    "notes AS (SELECT 'caf\u00e9 -- )' AS note /* ) */)",
    "dollar AS (SELECT $$ ) $$ AS note)",
    "hashed AS (SELECT 1 # )\n)",
)
_SCENARIO_TAILS: tuple[str, ...] = ("\nSELECT 1\n", "", ";", "\nSELECT 2", " -- end", ";\n")
_SCENARIO_KEYWORDS: tuple[str, ...] = (
    "WITH\n",
    "with ",
    "WITH RECURSIVE ",
    "w\u0131th ",
    "SELECT ",
)


def generated_scenario(*, rng: random.Random) -> str:
    """Return one scenario body mixing fixtures, checks, helpers and invalid CTEs."""

    ctes: list[str] = rng.sample(_SCENARIO_CTES, k=rng.randint(1, 5))
    return rng.choice(_SCENARIO_KEYWORDS) + ",\n".join(ctes) + rng.choice(_SCENARIO_TAILS)


def scenario_outcome(
    *,
    sql: str,
    syntax: SqlLexicalSyntax,
    engine: CompilerEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> object:
    """Extract one scenario under `engine`, or return Python's error text."""

    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine.value)
    try:
        return extract_sql_scenario_ctes(
            sql=sql, file_label="tests/scenarios/orders.sql", syntax=syntax
        )
    except CompileInputError as error:
        return str(error)


def native_scenario_answered(sql: str) -> bool:
    """Whether the native extraction answers instead of deferring to Python."""

    return _native.extract_sql_scenario_json(sql, "tests/scenarios/orders.sql") is not None


_TARGET_NAMES: tuple[str, ...] = ("orders", "customers", "channel_codes", "returns", "order_rows")
_KNOWN_NAMES: frozenset[str] = frozenset({"orders", "customers", "channel_codes", "order_rows"})


def generated_test_targets(
    *, rng: random.Random
) -> tuple[CompileModelSqlTestCtes, tuple[str, ...]]:
    """Return one model test payload and assertion targets mixing known and unknown names."""

    def names() -> tuple[str, ...]:
        return tuple(rng.sample(_TARGET_NAMES, k=rng.choice((0, 0, 1, 1, 2))))

    return (
        CompileModelSqlTestCtes(
            macro_mocks=dict.fromkeys(names(), "'x'"),
            mock_model_names=names(),
            mock_source_names=names(),
            mock_seed_names=names(),
            mock_table_function_names=names(),
            expected_model_names=names(),
        ),
        names(),
    )


def target_validation_outcome(
    *,
    payload: CompileModelSqlTestCtes,
    assertion_targets: tuple[str, ...],
    engine: CompilerEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> str | None:
    """Validate one payload's targets under `engine`, returning Python's error text."""

    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine.value)
    known: set[str] = set(_KNOWN_NAMES)
    try:
        validate_test_ctes(
            test_ctes=CompileSqlTestCtes(mode=SqlTestMode.MODEL, payload=payload),
            test_file=DiscoveredSqlTestFile(
                file_path=Path("/project/tests/unit/test_orders.sql"),
                relative_path=Path("tests/unit/test_orders.sql"),
                contents="",
                blocks=(),
            ),
            known_model_names=known,
            known_seed_names=known,
            known_source_names=known,
            known_table_function_names=known,
            loaded_macros=dict.fromkeys(known, cast(LoadedMacro, None)),
            assertion_target_model_names=assertion_targets,
        )
    except CompileInputError as error:
        return str(error)
    return None


_TYPES: tuple[object, ...] = (
    "STRING",
    " INTEGER ",
    "  ",
    "${coalesce(ENV:SQB_ATTACHMENTS_UNSET, 'DOUBLE')}",
    "${missing}",
    2,
)
_NAMES: tuple[object, ...] = ("raw_status", " amount ", "", "  ", 1)
_TEXTS: tuple[object, ...] = ("orders", " Orders. ", "", "  ", 3, None)
_SCHEMAS: tuple[object, ...] = (
    "udfs",
    "${coalesce(ENV:SQB_ATTACHMENTS_UNSET, 'udfs')}",
    1,
    None,
)


def _random_map(rng: random.Random, keys: tuple[object, ...]) -> dict[object, object]:
    return {rng.choice(keys): rng.choice(_TYPES) for _ in range(rng.randint(0, 3))}


def generated_function_header(*, rng: random.Random, python: bool) -> dict[str, object]:
    """Return SQL or Python function header values Python may accept or reject."""

    returns: tuple[object, ...] = (
        "STRING",
        " STRING ",
        "",
        {"table": _random_map(rng, _NAMES)},
        {"table": {"id": "INTEGER"}, "extra": 1},
        ["STRING"],
    )
    candidates: dict[str, object] = {
        "arguments": rng.choice((_random_map(rng, _NAMES), ["x"], None)),
        "returns": rng.choice((*returns, *returns[:2] * 3)),
        "tags": rng.choice((["orders", " sales "], ("orders",), [""], "orders", [1], None)),
        "description": rng.choice(_TEXTS),
        "database": rng.choice(_SCHEMAS),
        "schema": rng.choice(_SCHEMAS),
        "runtime_version": rng.choice(("3.12", " 3.12 ", "", None, 3)),
        "entry_point": rng.choice(("label", "", None)),
        "packages": rng.choice((["numpy"], ("numpy",), [""], "numpy", None)),
    }
    present: list[str] = rng.sample(sorted(candidates), k=rng.randint(4, len(candidates)))
    header: dict[str, object] = {key: candidates[key] for key in present}
    required: dict[bool, dict[str, object]] = {
        False: {"returns": "STRING"},
        True: {"returns": "STRING", "runtime_version": "3.12", "entry_point": "label"},
    }
    return {**required[python], **header}


def function_outcome(
    *,
    header_values: dict[str, object],
    python: bool,
    test_case: FunctionHeaderParityTestCase,
    engine: CompilerEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    """Attach one function under `engine`, returning its input or Python's error text."""

    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine.value)
    sql_file: DiscoveredSqlFunctionFile = DiscoveredSqlFunctionFile(
        file_path=Path("/project/functions/sql/order_label.sql"),
        relative_path=Path("functions/sql/order_label.sql"),
        contents="",
        header_values=header_values,
        body_sql="UPPER(raw_status)",
    )
    python_file: DiscoveredPythonFunctionFile = DiscoveredPythonFunctionFile(
        file_path=Path("/project/functions/python/order_label.py"),
        relative_path=Path("functions/python/order_label.py"),
        contents="",
        header_values=header_values,
        entry_point="label",
        body_python="def label(value):\n    return value\n",
    )
    sql_files: tuple[DiscoveredSqlFunctionFile, ...] = (sql_file,)[python:]
    python_files: tuple[DiscoveredPythonFunctionFile, ...] = (python_file,)[not python :]
    adapter: DuckDbAdapter = DuckDbAdapter()
    try:
        return repr(
            build_sql_function_inputs(
                discovered_inputs=DiscoveredProjectInputs(
                    project_config=ProjectConfig(
                        name="orders",
                        adapter="duckdb",
                        defaults=DefaultsConfig(database="analytics", schema="shared"),
                    ),
                    local_config=LocalConfig(),
                    sql_function_files=sql_files,
                    python_function_files=python_files,
                ),
                effective_vars={},
                effective_settings=SettingsConfig(),
                target_config=TargetConfig(database="warehouse", schema=test_case.target_schema),
                macro_context=_MACRO_CONTEXT,
                loaded_macros={},
                declaration_expansion=DeclarationExpansionContext(
                    declarations=DeclarationResolutionContext(),
                    value_renderer=adapter,
                    collection_rendering=CollectionRendering.VALUE_LIST,
                ),
                sql_lexical_syntax=adapter.sql_lexical_syntax,
                no_sql_validation=True,
                python_functions_inherit_default_namespace=test_case.inherit_default_namespace,
            )
        )
    except CompileInputError as error:
        return f"error: {error}"
