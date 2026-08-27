from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.compile._helpers.render.macros import (
    expand_sql_macros,
    find_macro_call_names,
    load_project_macros,
)
from sqlbuild.compiler.compile.models import (
    LoadedMacro,
    MacroContext,
)
from sqlbuild.compiler.discovery.models import DiscoveredMacroFile
from sqlbuild.compiler.scopes.types import ScopeKind
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    ExpandSqlMacrosErrorTestCase,
    ExpandSqlMacrosTestCase,
    FindMacroCallNamesTestCase,
    LoadProjectMacrosErrorTestCase,
    LoadProjectMacrosTestCase,
    MacroDependencyTestCase,
    ScopedMacroImportErrorTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import build_loaded_macros

_MACRO_CONTEXT: MacroContext = MacroContext(
    adapter_name="bigquery",
    sql_analysis_enabled=True,
    target_name="dev",
    vars={"project_name": "demo"},
)


@pytest.mark.parametrize(
    "test_case",
    [
        LoadProjectMacrosTestCase(
            description="exports only public ordinary functions owned by each macro module",
            macro_files={
                "macros/orders.py": """
from pathlib import Path
from urllib.parse import quote

_DEFAULT_LIMIT = 10


class _Formatter:
    pass


def _helper() -> str:
    return "order_id"


def order_columns() -> str:
    return _helper()
""".strip()
                + "\n",
            },
            expected_macro_names=("order_columns",),
        ),
        LoadProjectMacrosTestCase(
            description="composes absolute and relative project macro imports without re-export",
            macro_files={
                "macros/shared.py": "def shared(value: str) -> str:\n    return value.upper()\n",
                "macros/absolute.py": (
                    "from macros.shared import shared as render_shared\n\n"
                    "def absolute_macro() -> str:\n    return render_shared('absolute')\n"
                ),
                "macros/relative.py": (
                    "from .shared import shared\n\n"
                    "def relative_macro() -> str:\n    return shared('relative')\n"
                ),
            },
            expected_macro_names=("shared", "absolute_macro", "relative_macro"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_macro_modules_when_loading_then_exports_only_owned_public_functions(
    test_case: LoadProjectMacrosTestCase,
    tmp_path: Path,
) -> None:
    macro_files: list[DiscoveredMacroFile] = []
    relative_path: str
    contents: str
    for relative_path, contents in test_case.macro_files.items():
        file_path: Path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(contents, encoding="utf-8")
        macro_files.append(
            DiscoveredMacroFile(
                file_path=file_path,
                relative_path=Path(relative_path),
                contents=contents,
            )
        )

    loaded_macros: dict[str, LoadedMacro] = load_project_macros(tuple(macro_files))

    assert tuple(loaded_macros) == test_case.expected_macro_names


@pytest.mark.parametrize(
    "test_case",
    [
        MacroDependencyTestCase(
            description="tracks imported macro called through a private helper but not unused import",
            macro_files={
                "macros/shared.py": (
                    "def used(value: str) -> str:\n    return value.upper()\n\n"
                    "def unused() -> str:\n    return 'unused'\n"
                ),
                "macros/orders.py": (
                    "from macros.shared import used as render_used, unused\n\n"
                    "def _render(value: str) -> str:\n    return render_used(value)\n\n"
                    "def orders() -> str:\n    return _render('orders')\n"
                ),
            },
            macro_name="orders",
            expected_result="ORDERS",
            expected_dependencies=("used",),
        ),
        MacroDependencyTestCase(
            description="tracks public macro called through private helper in same module",
            macro_files={
                "macros/composed.py": (
                    "def base(value: str) -> str:\n    return value.upper()\n\n"
                    "def _helper(value: str) -> str:\n    return base(value)\n\n"
                    "def composed() -> str:\n    return _helper('composed')\n"
                )
            },
            macro_name="composed",
            expected_result="COMPOSED",
            expected_dependencies=("base",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_composed_macro_when_loading_then_tracks_actual_macro_dependencies(
    test_case: MacroDependencyTestCase,
    tmp_path: Path,
) -> None:
    macro_files: list[DiscoveredMacroFile] = []
    for relative_path, source in test_case.macro_files.items():
        file_path: Path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(source, encoding="utf-8")
        macro_files.append(DiscoveredMacroFile(file_path, Path(relative_path), source))

    loaded_macros: dict[str, LoadedMacro] = load_project_macros(tuple(macro_files))

    macro: LoadedMacro = loaded_macros[test_case.macro_name]
    assert macro.function() == test_case.expected_result
    assert tuple(item.name for item in macro.dependencies) == test_case.expected_dependencies


@pytest.mark.parametrize(
    "test_case",
    [
        ScopedMacroImportErrorTestCase(
            description="rejects sibling local macro import before execution",
            expected_error_fragment="not visible from the importer scope",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_inaccessible_scoped_macro_import_when_loading_then_rejects_before_execution(
    test_case: ScopedMacroImportErrorTestCase,
    tmp_path: Path,
) -> None:
    shared_source: str = "def shared() -> str:\n    return 'shared'\n"
    consumer_source: str = (
        "from pathlib import Path\n"
        "Path(__file__).parents[3].joinpath('executed').touch()\n"
        "from models.sales._local_macros.shared import shared\n\n"
        "def consumer() -> str:\n    return shared()\n"
    )
    shared_path: Path = tmp_path / "models/sales/_local_macros/shared.py"
    consumer_path: Path = tmp_path / "models/finance/_macros/consumer.py"
    shared_path.parent.mkdir(parents=True)
    consumer_path.parent.mkdir(parents=True)
    shared_path.write_text(shared_source, encoding="utf-8")
    consumer_path.write_text(consumer_source, encoding="utf-8")
    macro_files: tuple[DiscoveredMacroFile, ...] = (
        DiscoveredMacroFile(
            shared_path,
            Path("models/sales/_local_macros/shared.py"),
            shared_source,
            ScopeKind.LOCAL,
            Path("models"),
            Path("models/sales"),
            Path("models/sales/_local_macros"),
        ),
        DiscoveredMacroFile(
            consumer_path,
            Path("models/finance/_macros/consumer.py"),
            consumer_source,
            ScopeKind.INHERITED,
            Path("models"),
            Path("models/finance"),
            Path("models/finance/_macros"),
        ),
    )

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        load_project_macros(macro_files)

    assert not (tmp_path / "executed").exists()


@pytest.mark.parametrize(
    "test_case",
    [
        LoadProjectMacrosErrorTestCase(
            description="rejects a relative project module import before execution",
            macro_files={
                "macros/a_consumer.py": (
                    "from pathlib import Path\n"
                    "Path(__file__).parent.parent.joinpath('executed').touch()\n"
                    "from . import shared\n"
                ),
                "macros/shared.py": "def shared_macro() -> str:\n    return 'shared'\n",
            },
            expected_error_fragment="imports project package 'macros' instead of a macro module",
        ),
        LoadProjectMacrosErrorTestCase(
            description="rejects an import of a package containing project macros",
            macro_files={
                "macros/a_consumer.py": "import macros\n",
                "macros/shared.py": "def shared_macro() -> str:\n    return 'shared'\n",
            },
            expected_error_fragment="module imports are not supported",
        ),
        LoadProjectMacrosErrorTestCase(
            description="rejects missing project macro module before execution",
            macro_files={
                "macros/consumer.py": (
                    "from pathlib import Path\n"
                    "Path(__file__).parent.parent.joinpath('executed').touch()\n"
                    "from macros.missing import missing\n\n"
                    "def consumer() -> str:\n    return missing()\n"
                )
            },
            expected_error_fragment="imports project package 'macros.missing'",
        ),
        LoadProjectMacrosErrorTestCase(
            description="rejects project macro import cycle before execution",
            macro_files={
                "macros/first.py": (
                    "from pathlib import Path\n"
                    "Path(__file__).parent.parent.joinpath('executed').touch()\n"
                    "from macros.second import second\n\n"
                    "def first() -> str:\n    return second()\n"
                ),
                "macros/second.py": (
                    "from macros.first import first\n\ndef second() -> str:\n    return first()\n"
                ),
            },
            expected_error_fragment="Macro import cycle",
        ),
        LoadProjectMacrosErrorTestCase(
            description="rejects local macro call cycle before execution",
            macro_files={
                "macros/cycle.py": (
                    "from pathlib import Path\n"
                    "Path(__file__).parent.parent.joinpath('executed').touch()\n\n"
                    "def first() -> str:\n    return second()\n\n"
                    "def second() -> str:\n    return first()\n"
                )
            },
            expected_error_fragment="Macro call cycle.*first -> second -> first",
        ),
        LoadProjectMacrosErrorTestCase(
            description="rejects relative import escaping macro package before dependency executes",
            macro_files={
                "macros/consumer.py": (
                    "from ....macros.shared import shared\n\n"
                    "def consumer() -> str:\n    return shared()\n"
                ),
                "macros/shared.py": (
                    "from pathlib import Path\n"
                    "Path(__file__).parent.parent.joinpath('executed').touch()\n\n"
                    "def shared() -> str:\n    return 'shared'\n"
                ),
            },
            expected_error_fragment="escapes its top-level package",
        ),
        LoadProjectMacrosErrorTestCase(
            description="rejects dynamic local helper alias before execution",
            macro_files={
                "macros/helpers.py": (
                    "def _helper() -> str:\n    return 'helper'\n\n"
                    "def outer() -> str:\n"
                    "    alias = _helper\n"
                    "    return alias()\n"
                )
            },
            expected_error_fragment="uses local helper '_helper' dynamically",
        ),
        LoadProjectMacrosErrorTestCase(
            description="rejects module-level local helper alias before execution",
            macro_files={
                "macros/shared.py": "def shared() -> str:\n    return 'shared'\n",
                "macros/helpers.py": (
                    "from macros.shared import shared\n\n"
                    "def _helper() -> str:\n    return shared()\n\n"
                    "_alias = _helper\n\n"
                    "def outer() -> str:\n    return _alias()\n"
                ),
            },
            expected_error_fragment=(
                "uses local helper '_helper' outside an ordinary function body"
            ),
        ),
        LoadProjectMacrosErrorTestCase(
            description="rejects local helper call in macro default before execution",
            macro_files={
                "macros/shared.py": "def shared() -> str:\n    return 'shared'\n",
                "macros/helpers.py": (
                    "from macros.shared import shared\n\n"
                    "def _helper() -> str:\n    return shared()\n\n"
                    "def outer(value=_helper()) -> str:\n    return value\n"
                ),
            },
            expected_error_fragment=(
                "uses local helper '_helper' outside an ordinary function body"
            ),
        ),
        LoadProjectMacrosErrorTestCase(
            description="rejects module function replacing imported macro binding",
            macro_files={
                "macros/shared.py": "def shared() -> str:\n    return 'shared'\n",
                "macros/consumer.py": (
                    "from macros.shared import shared as _helper\n\n"
                    "def _helper() -> str:\n    return 'local'\n\n"
                    "def outer() -> str:\n    return _helper()\n"
                ),
            },
            expected_error_fragment="defines function '_helper' over an imported macro binding",
        ),
        LoadProjectMacrosErrorTestCase(
            description="rejects normalized project macro module path collision",
            macro_files={
                "macros/a.b.py": "def dotted() -> str:\n    return 'dotted'\n",
                "macros/a/b.py": "def nested() -> str:\n    return 'nested'\n",
            },
            expected_error_fragment="Macro module path collision for 'macros.a.b'",
        ),
        LoadProjectMacrosErrorTestCase(
            description="rejects public module owned constants",
            macro_files={"macros/orders.py": "DEFAULT_LIMIT = 10\n"},
            expected_error_fragment="declaration 'DEFAULT_LIMIT' must be underscore-private",
        ),
        LoadProjectMacrosErrorTestCase(
            description="rejects public module owned classes",
            macro_files={"macros/orders.py": "class Formatter:\n    pass\n"},
            expected_error_fragment="declaration 'Formatter' must be underscore-private",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_macro_module_when_loading_then_rejects_before_execution(
    test_case: LoadProjectMacrosErrorTestCase,
    tmp_path: Path,
) -> None:
    macro_files: list[DiscoveredMacroFile] = []
    relative_path: str
    contents: str
    for relative_path, contents in test_case.macro_files.items():
        file_path: Path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(contents, encoding="utf-8")
        macro_files.append(
            DiscoveredMacroFile(
                file_path=file_path,
                relative_path=Path(relative_path),
                contents=contents,
            )
        )

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        load_project_macros(tuple(macro_files))

    assert (tmp_path / "executed").exists() is test_case.expected_marker_exists


@pytest.mark.parametrize(
    "test_case",
    [
        ExpandSqlMacrosTestCase(
            description="uses macro override text instead of loaded macro function",
            macro_file_contents="""
def country() -> str:
    return "'CA'"
""".strip()
            + "\n",
            sql="SELECT @country() AS country",
            macro_overrides={"country": "'US'"},
            expected_sql="SELECT 'US' AS country",
        ),
        ExpandSqlMacrosTestCase(
            description="uses macro override text without evaluating macro arguments",
            macro_file_contents="""
def status(value: str) -> str:
    return value
""".strip()
            + "\n",
            sql="SELECT @status(@missing_nested()) AS status",
            macro_overrides={"status": "'paid'"},
            expected_sql="SELECT 'paid' AS status",
        ),
        ExpandSqlMacrosTestCase(
            description="expands nested macro arguments",
            macro_file_contents="""
def project_column() -> str:
    return "order_id"

def select_column(column_name: str) -> str:
    return f"SELECT {column_name}"
""".strip()
            + "\n",
            sql="@select_column(@project_column())",
            expected_sql="SELECT order_id",
        ),
        ExpandSqlMacrosTestCase(
            description="expands multiple nested macro arguments in one call",
            macro_file_contents="""
def left_column() -> str:
    return "order_id"

def right_column() -> str:
    return "customer_id"

def select_columns(left: str, right: str) -> str:
    return f"SELECT {left}, {right}"
""".strip()
            + "\n",
            sql="@select_columns(@left_column(), @right_column())",
            expected_sql="SELECT order_id, customer_id",
        ),
        ExpandSqlMacrosTestCase(
            description="expands ten nested macro calls in a chain",
            macro_file_contents="""
def step_1(value: str) -> str:
    return f"{value}_1"

def step_2(value: str) -> str:
    return f"{value}_2"

def step_3(value: str) -> str:
    return f"{value}_3"

def step_4(value: str) -> str:
    return f"{value}_4"

def step_5(value: str) -> str:
    return f"{value}_5"

def step_6(value: str) -> str:
    return f"{value}_6"

def step_7(value: str) -> str:
    return f"{value}_7"

def step_8(value: str) -> str:
    return f"{value}_8"

def step_9(value: str) -> str:
    return f"{value}_9"

def step_10(value: str) -> str:
    return f"SELECT {value}_10"
""".strip()
            + "\n",
            sql='@step_10(@step_9(@step_8(@step_7(@step_6(@step_5(@step_4(@step_3(@step_2(@step_1("base"))))))))))',
            expected_sql="SELECT base_1_2_3_4_5_6_7_8_9_10",
        ),
        ExpandSqlMacrosTestCase(
            description="ignores fake macro text inside line comments and strings",
            macro_file_contents="""
def project_columns() -> str:
    return "order_id, customer_id"
""".strip()
            + "\n",
            sql="""
-- @fake_macro()
SELECT '@fake_macro()' AS label, @project_columns() FROM raw_orders
""".strip(),
            expected_sql="""
-- @fake_macro()
SELECT '@fake_macro()' AS label, order_id, customer_id FROM raw_orders
""".strip(),
        ),
        ExpandSqlMacrosTestCase(
            description="ignores full email addresses and bare domains in comments and strings",
            macro_file_contents="""
def project_columns() -> str:
    return "order_id"
""".strip()
            + "\n",
            sql="""
-- contact: analyst@example.com and @example.com
SELECT
  'analyst@example.com' AS email_value,
  '@example.com' AS domain_value,
  @project_columns()
FROM raw_orders
""".strip(),
            expected_sql="""
-- contact: analyst@example.com and @example.com
SELECT
  'analyst@example.com' AS email_value,
  '@example.com' AS domain_value,
  order_id
FROM raw_orders
""".strip(),
        ),
        ExpandSqlMacrosTestCase(
            description="ignores fake macro text inside block comments and quoted identifiers",
            macro_file_contents="""
def project_columns() -> str:
    return "order_id"
""".strip()
            + "\n",
            sql="""
/* @fake_macro() */
SELECT `@fake_macro()` AS quoted_name, @project_columns() FROM raw_orders
""".strip(),
            expected_sql="""
/* @fake_macro() */
SELECT `@fake_macro()` AS quoted_name, order_id FROM raw_orders
""".strip(),
        ),
        ExpandSqlMacrosTestCase(
            description="passes compile macro context to ctx-aware macros",
            macro_file_contents="""
def adapter_name(ctx) -> str:
    return ctx.adapter_name
""".strip()
            + "\n",
            sql="SELECT @adapter_name() AS adapter_name",
            expected_sql="SELECT bigquery AS adapter_name",
        ),
        ExpandSqlMacrosTestCase(
            description="passes full compile macro context fields to ctx-aware macros",
            macro_file_contents="""
def context_summary(ctx) -> str:
    summary = (
        f"{ctx.adapter_name}|{ctx.sql_analysis_enabled}|"
        f"{ctx.target_name}|{ctx.vars['project_name']}"
    )
    return f"SELECT '{summary}'"
""".strip()
            + "\n",
            sql="@context_summary()",
            expected_sql="SELECT 'bigquery|True|dev|demo'",
        ),
        ExpandSqlMacrosTestCase(
            description="ignores generated call text inside comments and quoted strings",
            macro_file_contents=(
                "def literal_sql() -> str:\n    return \"'@quoted()' /* @commented() */\"\n"
            ),
            sql="SELECT @literal_sql()",
            expected_sql="SELECT '@quoted()' /* @commented() */",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_macro_variants_when_expanding_then_it_returns_expected_sql(
    test_case: ExpandSqlMacrosTestCase,
    tmp_path: Path,
) -> None:
    loaded_macros: dict[str, LoadedMacro] = build_loaded_macros(
        tmp_path, test_case.macro_file_contents
    )

    expanded_sql: str = expand_sql_macros(
        sql=test_case.sql,
        file_path=tmp_path / "models" / "orders.sql",
        loaded_macros=loaded_macros,
        macro_overrides=test_case.macro_overrides,
        macro_context=_MACRO_CONTEXT,
    )

    assert expanded_sql == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    [
        ExpandSqlMacrosErrorTestCase(
            description="raises when a ctx-aware macro is called with reserved ctx kwarg",
            macro_file_contents="""
def adapter_name(ctx) -> str:
    return ctx.adapter_name
""".strip()
            + "\n",
            sql="SELECT @adapter_name(ctx='manual') FROM raw_orders",
            expected_error_fragment="reserved for injected macro context",
        ),
        ExpandSqlMacrosErrorTestCase(
            description="raises when a top level macro returns a non string",
            macro_file_contents="""
def bad_macro() -> list[str]:
    return ["order_id"]
""".strip()
            + "\n",
            sql="SELECT @bad_macro() FROM raw_orders",
            expected_error_fragment="must return a SQL string when used directly in SQL",
        ),
        ExpandSqlMacrosErrorTestCase(
            description="raises when generated SQL contains an ordinary macro call",
            macro_file_contents=(
                "def outer_macro() -> str:\n    return '@inner_macro()'\n\n"
                "def inner_macro() -> str:\n    return 'order_id'\n"
            ),
            sql="SELECT @outer_macro() FROM raw_orders",
            expected_error_fragment="Compose macros with ordinary Python imports and function calls",
        ),
        ExpandSqlMacrosErrorTestCase(
            description="raises when generated SQL contains a constant reference",
            macro_file_contents=(
                "def generated_constant() -> str:\n    return '@const(\"limit\")'\n"
            ),
            sql="SELECT @generated_constant()",
            expected_error_fragment="Macro output must be final SQL",
        ),
        ExpandSqlMacrosErrorTestCase(
            description="raises when generated SQL contains an enum reference",
            macro_file_contents=(
                "def generated_enum() -> str:\n    return '@enum(\"status\").ACTIVE'\n"
            ),
            sql="SELECT @generated_enum()",
            expected_error_fragment="Macro output must be final SQL",
        ),
        ExpandSqlMacrosErrorTestCase(
            description="raises when macro override contains generated macro call",
            macro_file_contents="def outer() -> str:\n    return 'order_id'\n",
            sql="SELECT @outer()",
            expected_error_fragment="Macro output must be final SQL",
            macro_overrides={"outer": "@inner()"},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_sql_macro_usage_when_expanding_then_it_raises_clear_errors(
    test_case: ExpandSqlMacrosErrorTestCase,
    tmp_path: Path,
) -> None:
    loaded_macros: dict[str, LoadedMacro] = build_loaded_macros(
        tmp_path, test_case.macro_file_contents
    )

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        expand_sql_macros(
            sql=test_case.sql,
            file_path=tmp_path / "models" / "orders.sql",
            loaded_macros=loaded_macros,
            macro_overrides=test_case.macro_overrides,
            macro_context=_MACRO_CONTEXT,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        FindMacroCallNamesTestCase(
            description="returns real macro calls while ignoring declaration references",
            sql='SELECT @project_columns(), @const("region"), @enum("status").ACTIVE',
            expected_names=("project_columns",),
        ),
        FindMacroCallNamesTestCase(
            description="ignores at signs in quoted text comments and email addresses",
            sql="""
-- @line_comment() and line@example.com
/* @block_comment() */
SELECT '@single_quote()', "@double_quote", `@backtick`, @real_macro()
""".strip(),
            expected_names=("real_macro",),
        ),
        FindMacroCallNamesTestCase(
            description="returns unique macro names in encounter order",
            sql="SELECT @second(), @first(), @second()",
            expected_names=("second", "first"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_with_at_tokens_when_finding_macro_calls_then_returns_real_unique_names(
    test_case: FindMacroCallNamesTestCase,
) -> None:
    assert find_macro_call_names(test_case.sql) == test_case.expected_names
