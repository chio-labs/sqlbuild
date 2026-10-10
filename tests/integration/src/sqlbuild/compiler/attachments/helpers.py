"""Generated authored SQL and attached audits for the native attachment parity tests."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from sqlbuild.compiler.attachments.main._render_native_attached_audit import (
    render_native_attached_audit,
)
from sqlbuild.compiler.attachments.models import NativeAuditPolicies, NativeRenderedAudit
from sqlbuild.compiler.auditing.types import AuditRunScope, AuditSeverity
from sqlbuild.compiler.compile._helpers.attachment.audits import (
    resolve_audit_run_scope,
    resolve_audit_severity,
)
from sqlbuild.compiler.compile._helpers.refs.references import scan_sql_reference_calls
from sqlbuild.compiler.compile._helpers.render.arguments import render_parameterized_sql
from sqlbuild.compiler.compile._helpers.render.macros import find_macro_call_names
from sqlbuild.compiler.compile._helpers.sql_tests.native import extract_unexpanded_sql_test
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    SqlReferenceScan,
)
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax

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
    "@values\u2003(",
    "@'values'\u3000",
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
    ("placed", 3.5, float("inf")),
    [("placed",), ["shipped"]],
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
    ("column", ("status",)),
    ("column", ["amount"]),
)


@dataclass(frozen=True)
class GeneratedAudit:
    """One attachment: SQL, arguments and authored policies."""

    sql_body: str
    evidence_sql: str
    implicit_arguments: dict[str, str]
    explicit_arguments: dict[object, object]
    instance_severity: str | None
    default_severity: str | None
    instance_run_scope: str | None
    default_run_scope: str | None


@dataclass(frozen=True)
class AuditParity:
    """Python's rendering (or error text) and the native rendering."""

    audit: GeneratedAudit
    python: tuple[object, ...] | str
    native: NativeRenderedAudit


def generated_audit(*, rng: random.Random) -> GeneratedAudit:
    """Return one attachment mixing parameter shapes, argument values and policies."""

    rare: dict[str, object] = dict(rng.choices(_RARE, k=int(rng.random() < 0.3)))
    explicit: dict[object, object] = {
        "values": rng.choice(_VALUES),
        "limit_rows": rng.choice(_VALUES),
    }
    explicit.update(filter(_is_column_override, rare.items()))
    explicit.update(dict.fromkeys(rng.choices((7,), k=int(rng.random() < 0.1)), "x"))
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
            labels=("models/orders.sql", "floor"),
            sql_body=audit.sql_body,
            evidence_sql=audit.evidence_sql,
            implicit_arguments=audit.implicit_arguments,
            explicit_arguments=cast(dict[str, object], audit.explicit_arguments),
            policies=NativeAuditPolicies(
                has_thresholds=False,
                threshold_error=False,
                instance_severity=audit.instance_severity,
                default_severity=audit.default_severity,
                instance_run_scope=audit.instance_run_scope,
                default_run_scope=audit.default_run_scope,
            ),
        ),
    )


def native_outcome(parity: AuditParity) -> tuple[object, ...] | str:
    """The native rendering or error spelled like Python's, with the run scope it selects."""

    rendered: NativeRenderedAudit = parity.native
    return rendered.render_error or rendered.policy_error or _native_rendering(parity)


def _native_rendering(parity: AuditParity) -> tuple[object, ...]:
    rendered: NativeRenderedAudit = parity.native
    run_scope: str | None = {
        "instance": parity.audit.instance_run_scope,
        "default": parity.audit.default_run_scope,
    }.get(rendered.run_scope_source, AuditRunScope.DELTA_AND_FINAL)
    return (rendered.sql_body, rendered.evidence_sql, AuditSeverity(rendered.severity), run_scope)


def _python_rendering(audit: GeneratedAudit) -> tuple[object, ...] | str:
    owner: Path = Path("models/orders.sql")
    implicit: dict[object, object] = cast(dict[object, object], audit.implicit_arguments)
    overrides: list[object] = [
        name
        for name, value in filter(
            lambda item: item[0] in implicit and implicit[item[0]] != item[1],
            audit.explicit_arguments.items(),
        )
    ]
    try:
        for name in overrides[:1]:
            raise CompileInputError(
                f"{owner} audit 'floor' must not override implicit {name} from attached context"
            )
        merged: dict[str, object] = cast(
            dict[str, object], {**audit.implicit_arguments, **audit.explicit_arguments}
        )
        rendered: tuple[str, ...] = tuple(
            render_parameterized_sql(
                sql=sql,
                arguments=merged,
                owner_label=str(owner),
                definition_label="generic audit 'floor'",
            )
            for sql in (audit.sql_body, audit.evidence_sql)
        )
        severity: AuditSeverity = resolve_audit_severity(
            instance_severity=audit.instance_severity,
            default_severity=audit.default_severity,
            audit_label=f"{owner} audit 'floor'",
        )
        run_scope: str = resolve_audit_run_scope(
            instance_run_scope=audit.instance_run_scope,
            default_run_scope=audit.default_run_scope,
        )
    except CompileInputError as error:
        return str(error)
    return (*rendered, severity, run_scope)


_MACRO_PIECES: tuple[str, ...] = (
    "a",
    "@m(1)",
    "@m (1)",
    "@ab (1)",
    "@ab cd(1)",
    "@enum('Status', 'PAID')",
    "@const(@m(1))",
    "@var('x')",
    '@param("p")',
    "@@region",
    "@m$x(1)",
    '@"m"(1)',
    "@\u00e9t\u00e9(1)",
    "@m\u00a0(1)",
    "@mm\u3000(1)",
    "@mm\x1c(1)",
    "'@m(1)'",
    "-- @m(1)\n",
    "/* @m(1) */",
    "$$@m(1)$$",
    "$t$@m(1)$t$",
    "`@m(1)`",
    '"@m(1)"',
    "x@m(1)",
    "@m(@n(1))",
    "@_m(1)",
    "@1m(1)",
    "@\u216b(1)",
)
_REFERENCE_PIECES: tuple[str, ...] = (
    "a",
    '__udf("order_label")(a)',
    '__table_fn("order_rows")(1)',
    '__ref("orders")',
    '__source("events", "orders")',
    '__source("events")',
    '__dbt_ref("shop", "orders")',
    '__dbt_ref("orders")',
    "__dbt_ref(orders)",
    "__udf('order_label')",
    '__udf("order_label", 1)',
    "__udf(order_label)",
    '__udf("")',
    '__udf(  "order_label" )',
    '__table_fn("order_rows")',
    '__table_fn("order_rows")\u00a0(1)',
    '__table_fn("order_rows") (1)',
    '__UDF("order_label")',
    '__udf ("order_label")',
    'x__udf("order_label")(a)',
    "'__udf(\"order_label\")'",
    '-- __udf("order_label")\n',
    '# __udf("order_label")\n',
    '// __udf("order_label")\n',
    '/* /* __udf("order_label") */ */',
    "'it''s'",
    '$$__udf("order_label")$$',
    '`__udf("order_label")`',
)
_LOGIC_REFERENCE_KINDS: frozenset[str] = frozenset({"udf", "table_fn"})
BODY_CALL_SYNTAXES: dict[str, SqlLexicalSyntax] = {
    "generic": SqlLexicalSyntax(),
    "duckdb": SqlLexicalSyntax(escape_string_prefix=True, nested_block_comments=True),
    "bigquery": SqlLexicalSyntax(
        backslash_escape_quotes=frozenset({"'", '"', "`"}),
        triple_quoted_strings=True,
        line_comment_prefixes=frozenset({"--", "#"}),
    ),
    "snowflake": SqlLexicalSyntax(
        backslash_escape_quotes=frozenset({"'"}), line_comment_prefixes=frozenset({"--", "//"})
    ),
}


def generated_macro_body(*, rng: random.Random) -> str:
    """Return one helper body mixing macro calls and macro-like text."""

    pieces: list[str] = [rng.choice(_MACRO_PIECES) for _ in range(rng.randint(1, 3))]
    return "SELECT " + " + ".join(pieces) + " AS a"


def generated_reference_body(*, rng: random.Random) -> str:
    """Return one helper body mixing valid, malformed and hidden reference calls."""

    pieces: list[str] = [rng.choice(_REFERENCE_PIECES) for _ in range(rng.randint(1, 3))]
    return "SELECT " + " + ".join(pieces) + "\n AS a"


def python_macro_outcome(*, body: str) -> str:
    """Whether expansion's macro scanner finds a call in `body`, or that it raises."""

    try:
        return f"calls macros {bool(find_macro_call_names(body))}"
    except CompileInputError:
        return "unscannable"


def macro_scannable(body: str) -> bool:
    """Whether expansion's macro scanner reads `body` without raising."""

    return python_macro_outcome(body=body) != "unscannable"


def native_macro_outcome(*, body: str) -> str:
    """Whether the raw extractor rejects a macro-test helper `body` for calling macros."""

    try:
        _ = extract_unexpanded_sql_test(
            sql=(
                f"WITH h AS ({body}), __macro_actual__ AS (SELECT @m(1) AS a), "
                "__macro_expected__ AS (SELECT 1 AS a)"
            ),
            file_label="tests/unit/test_logic.sql",
            mode=SqlTestMode.MACRO,
            syntax=SqlLexicalSyntax(),
        )
    except CompileInputError as error:
        return f"calls macros {'must not call macros' in str(error)}"
    return "calls macros False"


def python_reference_outcome(*, body: str, syntax: SqlLexicalSyntax) -> str:
    """Python's first `__udf`/`__table_fn` kind in `body`, or whether it has P012 calls."""

    try:
        scan: SqlReferenceScan = scan_sql_reference_calls(sql=body, syntax=syntax)
    except CompileInputError as error:
        return f"error: {error}"
    kinds: list[str] = [str(reference.ref_kind) for reference in scan.references]
    kind: str | None = next(filter(_LOGIC_REFERENCE_KINDS.__contains__, kinds), None)
    return (kind and f"calls {kind}") or f"malformed calls {bool(scan.invalid_calls)}"


def native_reference_outcome(*, body: str, syntax: SqlLexicalSyntax) -> str:
    """The raw extractor's reading of a UDF-test helper `body`, as `python_reference_outcome`."""

    try:
        _, invalid_calls = extract_unexpanded_sql_test(
            sql=(
                f"WITH h AS ({body}), __udf_actual__ AS (SELECT 1 AS a), "
                "__udf_expected__ AS (SELECT 1 AS a)"
            ),
            file_label="tests/unit/test_logic.sql",
            mode=SqlTestMode.UDF,
            syntax=syntax,
        )
    except CompileInputError as error:
        called: re.Match[str] | None = re.search(r"must not call (\w+);", str(error))
        return (called and f"calls {called.group(1)}") or f"error: {error}"
    return f"malformed calls {invalid_calls}"
