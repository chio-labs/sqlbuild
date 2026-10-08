"""Generated authored SQL and attached audits for the native attachment parity tests."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
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
from sqlbuild.compiler.compile._helpers.render.sql_vars import expand_authored_sql_result
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import (
    AuthoredSqlExpansionResult,
    CompileAdapterContext,
    CompileProjectInputs,
    MacroContext,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.frontier.types import CompilerEngine
from sqlbuild.spec.contracts.main.resolve_effective_collection_rendering import (
    resolve_effective_collection_rendering,
)
from sqlbuild.sql_values.types import CollectionRendering
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
        "    expression: \"(SELECT 1 AS id, '@@region' AS region)\"\n"
        "    columns:\n      - name: id\n        type: INTEGER\n        audits:\n"
        "          - accepted_values:\n              values: [1, 2]\n"
        "      - name: region\n        type: VARCHAR\n"
    ),
    "functions/sql/order_label.sql": (
        'FUNCTION (\n  description "Label an order status.",\n'
        f"  schema \"${{coalesce(ENV:{_MISSING_ENV}, 'udfs')}}\",\n"
        "  arguments (raw_status STRING),\n  returns STRING,\n);\n\nUPPER(raw_status)\n"
    ),
    "audits/generic/amount_floor.sql": (
        'AUDIT ();\n\nSELECT *\nFROM __ref("@model")\nWHERE @column < @minimum '
        "AND label <> @'label'\n"
    ),
    "models/orders.sql": (
        'MODEL (\n  materialized table,\n  description "Orders.",\n'
        '  audits [amount_floor (column amount, minimum -5, label "it\'s", severity warn)],\n'
        ");\n\nSELECT c.id, 1.5 AS amount, c.label\n"
        'FROM __seed("channel_codes") c\nJOIN __source("order_events") e ON e.id = c.id\n'
    ),
}


def attachment_engine_outcome(
    *,
    project_dir: Path,
    engine: CompilerEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[frozenset[str], str]:
    """Build compile inputs under `engine`; return the native entries called and the outcome."""

    for relative_path, contents in ATTACHMENT_PROJECT.items():
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    called: set[str] = set()
    for name in NATIVE_ATTACHMENT_ENTRIES:
        monkeypatch.setattr(_native, name, _recorded(called=called, name=name))
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine.value)
    inputs: CompileProjectInputs = _compile_inputs(project_dir=project_dir)
    return frozenset(called), repr(
        (
            inputs.seed_inputs,
            inputs.source_inputs,
            inputs.sql_function_inputs,
            inputs.audit_inputs,
            inputs.test_inputs,
            inputs.scenario_inputs,
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


def _recorded(*, called: set[str], name: str) -> Callable[..., object]:
    entry: Callable[..., object] = getattr(_native, name)

    def recorded(*args: object) -> object:
        called.add(name)
        return entry(*args)

    return recorded
