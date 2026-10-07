"""Macro-heavy projects, engine-switched render runs and bridged-expansion outcomes."""

from __future__ import annotations

import random
import re
from collections.abc import Callable
from contextvars import Token
from functools import partial
from pathlib import Path

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile._helpers.render.macros import expand_sql_macros_result
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import (
    CompileAdapterContext,
    CompileProjectInputs,
    LoadedMacro,
    MacroContext,
    MacroExpansionResult,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.frontier._helpers.stage_capture import render_stage_capture
from sqlbuild.compiler.frontier.constants import (
    COMPILER_ENGINE_ENV_VAR,
    STAGE_CAPTURE_INVOCATION_ID_MASK,
    STAGE_CAPTURE_INVOCATION_ID_PATTERN,
)
from sqlbuild.compiler.frontier.main._compile_frontier import compile_frontier
from sqlbuild.compiler.frontier.types import CompilerStage
from sqlbuild.compiler.macro_bridge.classes.macro_bridge import MacroBridge
from sqlbuild.compiler.macro_bridge.constants import ACTIVE_MACRO_BRIDGE
from sqlbuild.compiler.scopes.models import ResourceIdentity
from sqlbuild.compiler.scopes.types import ResourceKind
from sqlbuild.spec.contracts.main.resolve_effective_collection_rendering import (
    resolve_effective_collection_rendering,
)

MACRO_CALL_LOG_ENV_VAR: str = "SQLBUILD_TEST_MACRO_CALL_LOG"
_RUN_ID_PATTERN: re.Pattern[str] = re.compile(r'"run_id": "[^"]*"')
_DIFFERENTIAL_FRAGMENTS: tuple[str, ...] = (
    "@m('a')", "@m(1)", "@m()", "@mm(2)", "@mm (2)", "@m (1)", "@n(@m('b'))", "@n(@m(@n()))",
    "@n(@mm(3), '@m(4)')", "@tag(__ref('orders'))", "@tag(__seed('rates'))",
    "@tag(__ref('customers'))", "@cols(__ref('orders'))", "@gen()", "@nope(1)", "@m(x)",
    "@ab c(1)", "@m('é')", "'@m(1)'", "-- @m(1)\n", "/* @n() */", "$$@m()$$", "`@m()`", "@@v",
    "@", " ", "\n", "\u3000", "é", "'", "(", ")", "SELECT ", ", ", "\"q\"",
)  # fmt: skip
_DIFFERENTIAL_FILE: Path = Path("models/orders_summary.sql")

MACRO_BRIDGE_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "bridge_demo"\n'
        'adapter = "duckdb"\n'
        'default_target = "dev"\n\n'
        "[connection]\n"
        'database = "bridge.duckdb"\n\n'
        "[vars]\n"
        'region = "north"\n\n'
        "[targets.dev]\n"
        'schema = "analytics"\n\n'
        "[settings]\n"
        "sql_analysis = false\n\n"
        "[scopes]\n"
        "enforce_placement = false\n"
    ),
    "macros/common.py": (
        '"""Shared macros for the bridge demo."""\n\n'
        "import os\n\n\n"
        "def cents(column: str) -> str:\n"
        '    """Convert an amount to cents."""\n'
        '    return f"{column} * 100"\n\n\n'
        "def wrap(expression: str) -> str:\n"
        '    """Parenthesise an expression."""\n'
        '    return f"({expression})"\n\n\n'
        "def region_filter(ctx) -> str:\n"
        '    """Compare the region column with the configured region."""\n'
        "    return f\"region = '{ctx.vars['region']}'\"\n\n\n"
        "def scale(ctx, column: str) -> str:\n"
        '    """Scale a column by every visible rate."""\n'
        '    return f"{column} * {sum(ctx.constants.values())}"\n\n\n'
        "def visible_constants(ctx) -> str:\n"
        '    """List the visible constants."""\n'
        "    return repr(', '.join(ctx.constants))\n\n\n"
        "def status_code(ctx) -> str:\n"
        '    """Render the placed status."""\n'
        "    return ctx.render_enum_member(enum_name='order_status', member_name='PLACED')\n\n\n"
        "def optional_label(ctx) -> str:\n"
        '    """Read an optional constant."""\n'
        "    return repr(ctx.constants.get('missing_label', 'none'))\n\n\n"
        "def columns_of(relation) -> str:\n"
        '    """Select every column of a relation."""\n'
        '    return f"SELECT * FROM {relation}"\n\n\n'
        "def ref_tag(relation) -> str:\n"
        '    """Expose the in-expansion relation placeholder text."""\n'
        "    return repr(str(relation).upper())\n\n\n"
        "def generated_join() -> str:\n"
        '    """Emit a reference instead of receiving it."""\n'
        "    return '(SELECT id FROM __ref(\"customers\"))'\n\n\n"
        "def logged(column: str) -> str:\n"
        '    """Record each execution in the test log."""\n'
        f'    path = os.environ.get("{MACRO_CALL_LOG_ENV_VAR}")\n'
        "    if path:\n"
        '        with open(path, "a", encoding="utf-8") as log:\n'
        '            log.write(column + "\\n")\n'
        "    return column\n"
    ),
    "enums/order_status.sql": (
        'ENUM (\n  name order_status,\n  members (PLACED "placed", SHIPPED "shipped"),\n);\n'
    ),
    "models/north/_sqlbuild/_macros/fmt.py": (
        'def fmt(value: str) -> str:\n    """Label a value."""\n    return f"\'north:{value}\'"\n'
    ),
    "constants/base_rate.sql": "CONSTANT (name base_rate, value 1);\n",
    "models/north/_sqlbuild/_constants/north_rate.sql": "CONSTANT (name north_rate, value 10);\n",
    "models/south/_sqlbuild/_constants/south_rate.sql": "CONSTANT (name south_rate, value 20);\n",
    "models/shared/customers.sql": (
        "MODEL (description \"Customers\");\n\nSELECT 1 AS id, 2 AS amount, 'north' AS region\n"
    ),
    "models/shared/orders_source.sql": (
        'MODEL (description "Orders source");\n\nSELECT 1 AS id, 3 AS amount\n'
    ),
    "hooks/sql/stamp.sql": (
        "HOOK (description \"Stamp a value\");\n\nSELECT @cents('2') AS stamped\n"
    ),
    "functions/sql/udf__cents_of.sql": (
        "FUNCTION (\n"
        '  description "Convert a value to cents",\n'
        "  arguments (v INTEGER),\n"
        "  returns INTEGER,\n"
        ");\n\n"
        '@cents("v")\n'
    ),
    "audits/generic/positive_cents.sql": (
        'AUDIT ();\n\nSELECT *\nFROM __ref("@model")\nWHERE @cents("amount") < 0\n'
    ),
    "sources/raw.yml": (
        "sources:\n"
        "  - name: raw__payments\n"
        "    description: Payments\n"
        "    expression: |\n"
        "      SELECT @cents('5') AS amount_cents, @wrap(@cents('6')) AS wrapped\n"
    ),
    "tests/unit/test_cents_macro.sql": (
        'TEST (mode macro, name "converts_to_cents");\n\n'
        "WITH\n"
        "__macro_actual__ AS (\n"
        '  SELECT @cents("3") AS cents\n'
        "),\n"
        "__macro_expected__ AS (\n"
        "  SELECT 300 AS cents\n"
        ")\n"
        "SELECT 1\n"
    ),
}

_REGION_MODEL_BODY: str = (
    "SELECT\n"
    '  @cents("amount") AS amount_cents,\n'
    '  @wrap(@cents("amount")) AS wrapped,\n'
    '  @scale("amount") AS scaled,\n'
    "  @visible_constants() AS visible,\n"
    "  {label} AS label,\n"
    "  @region_filter() AS region_check,\n"
    "  @status_code() AS status_value,\n"
    "  @optional_label() AS optional_label,\n"
    "  {ref_tags},\n"
    '  @logged("amount") AS logged_amount,\n'
    "  'quoted @cents(1)' AS quoted -- @cents(2)\n"
    'FROM (@columns_of(__ref("customers"))) AS c\n'
    "WHERE id IN @generated_join()\n"
)
_NORTH_REF_TAGS: str = '@ref_tag(__ref("orders_source")) AS first_tag'
_SOUTH_REF_TAGS: str = (
    '@ref_tag(__ref("customers")) AS first_tag, @ref_tag(__ref("orders_source")) AS second_tag'
)


def _region_model(*, description: str, hooks: str, ref_tags: str, label: str) -> str:
    return (
        f'MODEL (\n  description "{description}",\n{hooks}'
        "  audits [positive_cents ()],\n);\n\n"
        + _REGION_MODEL_BODY.format(ref_tags=ref_tags, label=label)
    )


_NORTH_HOOKS: str = (
    "  pre_hooks [\n"
    "    inline_sql(\"SELECT @cents('1') AS hook_value\"),\n"
    '    sql("stamp"),\n'
    "  ],\n"
)
MACRO_BRIDGE_PROJECT_FILES.update(
    {
        "models/north/orders_north.sql": _region_model(
            description="North orders",
            hooks=_NORTH_HOOKS,
            ref_tags=_NORTH_REF_TAGS,
            label='@fmt("x")',
        ),
        "models/north/orders_north_copy.sql": _region_model(
            description="North orders copy",
            hooks=_NORTH_HOOKS,
            ref_tags=_NORTH_REF_TAGS,
            label='@fmt("x")',
        ),
        "models/south/orders_south.sql": _region_model(
            description="South orders", hooks="", ref_tags=_SOUTH_REF_TAGS, label="'south'"
        ),
    }
)


def write_project(*, root: Path, files: dict[str, str]) -> Path:
    """Write project files below `root` and return it."""

    for relative_path, content in files.items():
        path: Path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(content, encoding="utf-8")
    return root


def render_compile_inputs(
    *, project_dir: Path, engine: str, monkeypatch: pytest.MonkeyPatch
) -> CompileProjectInputs:
    """Render the project's compile inputs through the frontier under one compiler engine."""

    with monkeypatch.context() as patch:
        patch.setenv(COMPILER_ENGINE_ENV_VAR, engine)
        discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
        adapter: DuckDbAdapter = DuckDbAdapter()
        return compile_frontier(
            until=CompilerStage.COMPILE_PROJECT_INPUTS,
            python_stage=partial(
                build_compile_inputs,
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
                resolved_connection={},
                defer_model_sql_validation=True,
                no_cache=True,
            ),
        )


def comparable_capture(inputs: CompileProjectInputs) -> str:
    """Render compile inputs as canonical JSON without the per-run identifier."""

    return STAGE_CAPTURE_INVOCATION_ID_PATTERN.sub(
        STAGE_CAPTURE_INVOCATION_ID_MASK,
        _RUN_ID_PATTERN.sub('"run_id": "<run>"', render_stage_capture(inputs)),
    )


def render_error(
    *, project_dir: Path, engine: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[type[BaseException], str, type[object]]:
    """Render the project under one engine and describe the error it raises."""

    with pytest.raises(CompileInputError) as raised:
        _ = render_compile_inputs(project_dir=project_dir, engine=engine, monkeypatch=monkeypatch)
    return type(raised.value), str(raised.value), type(raised.value.__cause__)


def _wrap_m(value: object = "") -> str:
    return f"m<{value}>"


def _wrap_n(value: object = "", label: object = "") -> str:
    return f"n[{value}{label}]"


def _tag(relation: object) -> str:
    return repr(str(relation).upper())


def _cols(relation: object) -> str:
    return f"SELECT * FROM {relation}"


def _generated() -> str:
    return '(SELECT id FROM __ref("orders"))'


def _loaded_macro(*, name: str, function: Callable[..., object]) -> LoadedMacro:
    path: Path = Path(f"macros/{name}.py")
    return LoadedMacro(
        name=name, file_path=path, relative_path=path, raw_source="", function=function
    )


DIFFERENTIAL_MACROS: dict[str, LoadedMacro] = {
    name: _loaded_macro(name=name, function=function)
    for name, function in (
        ("m", _wrap_m),
        ("mm", _wrap_m),
        ("n", _wrap_n),
        ("tag", _tag),
        ("cols", _cols),
        ("gen", _generated),
    )
}
_DIFFERENTIAL_CONTEXT: MacroContext = MacroContext(
    adapter_name="duckdb", sql_analysis_enabled=False, target_name=None
)


class ExpansionFailureCapture:
    """Swallow and keep the compile input error a block raises."""

    def __init__(self) -> None:
        self.failure: BaseException | None = None

    def __enter__(self) -> ExpansionFailureCapture:
        return self

    def __exit__(self, error_type: object, error: BaseException | None, traceback: object) -> bool:
        self.failure = error
        return isinstance(error, CompileInputError)


def random_macro_sql(*, rng: random.Random) -> str:
    """Return SQL text mixing valid and malformed macro calls, quotes, comments and Unicode."""

    return "".join(rng.choice(_DIFFERENTIAL_FRAGMENTS) for _ in range(rng.randint(0, 12)))


def expansion_outcome(*, sql: str, bridge: MacroBridge | None) -> tuple[object, ...]:
    """Expand `sql` with or without the bridge; return the result facts or the error."""

    token: Token[object | None] = ACTIVE_MACRO_BRIDGE.set(bridge)
    capture: ExpansionFailureCapture = ExpansionFailureCapture()
    rendered: list[tuple[object, ...]] = [()]
    with capture:
        result: MacroExpansionResult = expand_sql_macros_result(
            sql=sql,
            file_path=_DIFFERENTIAL_FILE,
            loaded_macros=DIFFERENTIAL_MACROS,
            macro_context=_DIFFERENTIAL_CONTEXT,
            consumer=ResourceIdentity(ResourceKind.MODEL, "orders_summary"),
        )
        rendered[0] = (
            result.sql,
            result.spans,
            result.dependencies,
            result.usages,
            result.argument_references,
        )
    ACTIVE_MACRO_BRIDGE.reset(token)
    return {
        True: rendered[0],
        False: (type(capture.failure).__name__, str(capture.failure)),
    }[capture.failure is None]
