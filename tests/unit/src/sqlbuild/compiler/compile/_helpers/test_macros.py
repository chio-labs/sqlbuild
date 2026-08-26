from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.compile._helpers.render.macros import (
    expand_sql_macros,
    expand_sql_macros_result,
    find_macro_call_names,
    load_project_macros,
)
from sqlbuild.compiler.compile.models import (
    LoadedMacro,
    MacroContext,
    MacroExpansionResult,
)
from sqlbuild.compiler.discovery.models import DiscoveredMacroFile
from sqlbuild.compiler.scopes.types import ScopeKind
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    ExpandSqlMacrosErrorTestCase,
    ExpandSqlMacrosTestCase,
    FindMacroCallNamesTestCase,
    LoadProjectMacrosErrorTestCase,
    LoadProjectMacrosTestCase,
    ScopedMacroExpansionErrorTestCase,
    ScopedMacroExpansionTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import (
    build_loaded_macros,
    build_scoped_macro_resolver,
)

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
        LoadProjectMacrosErrorTestCase(
            description="rejects an absolute import of another project macro before execution",
            macro_files={
                "macros/a_consumer.py": (
                    "from pathlib import Path\n"
                    "Path(__file__).parent.parent.joinpath('executed').touch()\n"
                    "from macros.shared import shared_macro\n"
                ),
                "macros/shared.py": "def shared_macro() -> str:\n    return 'shared'\n",
            },
            expected_error_fragment="must not import project macro module 'macros.shared'",
        ),
        LoadProjectMacrosErrorTestCase(
            description="rejects a relative import of another project macro before execution",
            macro_files={
                "macros/a_consumer.py": "from . import shared\n",
                "macros/shared.py": "def shared_macro() -> str:\n    return 'shared'\n",
            },
            expected_error_fragment="must not import project macro module 'macros.shared'",
        ),
        LoadProjectMacrosErrorTestCase(
            description="rejects an import of a package containing project macros",
            macro_files={
                "macros/a_consumer.py": "import macros\n",
                "macros/shared.py": "def shared_macro() -> str:\n    return 'shared'\n",
            },
            expected_error_fragment="must not import project macro module 'macros'",
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
            description="recursively expands macro calls emitted by macro output",
            macro_file_contents="""
def outer_macro() -> str:
    return "@inner_macro()"

def inner_macro() -> str:
    return "order_id"
""".strip()
            + "\n",
            sql="SELECT @outer_macro() FROM raw_orders",
            expected_sql="SELECT order_id FROM raw_orders",
        ),
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


@pytest.mark.parametrize(
    "test_case",
    [
        ScopedMacroExpansionTestCase(
            description="callee sees same-owner inherited local and global macros",
            definitions={
                "global_value": ("global", ScopeKind.GLOBAL, None, "macros/global_value.py"),
                "same_scope": (
                    "same",
                    ScopeKind.INHERITED,
                    "models/marts",
                    "models/marts/_macros/same_scope.py",
                ),
                "same_local": (
                    "local",
                    ScopeKind.LOCAL,
                    "models/marts",
                    "models/marts/_local_macros/same_local.py",
                ),
                "outer": (
                    "@same_scope() || @same_local() || @global_value()",
                    ScopeKind.INHERITED,
                    "models/marts",
                    "models/marts/_macros/outer.py",
                ),
            },
            expected_sql="SELECT same || local || global",
            expected_dependencies=("outer", "same_scope", "same_local", "global_value"),
            expected_usages=(
                ("outer", "same_scope"),
                ("outer", "same_local"),
                ("outer", "global_value"),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_scoped_composition_when_expanding_then_uses_callee_lexical_scope(
    test_case: ScopedMacroExpansionTestCase,
    tmp_path: Path,
) -> None:
    loaded, resolver = build_scoped_macro_resolver(
        tmp_path=tmp_path, definitions=test_case.definitions
    )

    result: MacroExpansionResult = expand_sql_macros_result(
        sql="SELECT @outer()",
        file_path=tmp_path / "models/marts/finance/orders.sql",
        loaded_macros=loaded,
        macro_context=_MACRO_CONTEXT,
        declaration_resolver=resolver,
    )

    assert result.sql == test_case.expected_sql
    assert tuple(item.name for item in result.dependencies) == test_case.expected_dependencies
    assert (
        tuple((item.consumer.name, item.declaration.name) for item in result.usages)
        == test_case.expected_usages
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ScopedMacroExpansionErrorTestCase(
            description="global macro cannot emit scoped call",
            definitions={
                "scoped_value": (
                    "scoped",
                    ScopeKind.INHERITED,
                    "models/marts",
                    "models/marts/_macros/scoped_value.py",
                ),
                "global_outer": (
                    "@scoped_value()",
                    ScopeKind.GLOBAL,
                    None,
                    "macros/global_outer.py",
                ),
            },
            sql="SELECT @global_outer()",
            expected_error_fragment=(
                r"scoped_value.*inaccessible.*models/marts/_macros/scoped_value.py.*"
                r"scope owner 'models/marts'"
            ),
        ),
        ScopedMacroExpansionErrorTestCase(
            description="recursive output reports complete cycle",
            definitions={
                "first": ("@second()", ScopeKind.GLOBAL, None, "macros/first.py"),
                "second": ("@first()", ScopeKind.GLOBAL, None, "macros/second.py"),
            },
            sql="SELECT @first()",
            expected_error_fragment=(
                r"first -> second -> first.*macros/first.py -> macros/second.py -> macros/first.py"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_global_macro_emits_scoped_call_when_expanding_then_reports_inaccessible(
    test_case: ScopedMacroExpansionErrorTestCase,
    tmp_path: Path,
) -> None:
    loaded, resolver = build_scoped_macro_resolver(
        tmp_path=tmp_path, definitions=test_case.definitions
    )

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        expand_sql_macros(
            sql=test_case.sql,
            file_path=tmp_path / "models/marts/finance/orders.sql",
            loaded_macros=loaded,
            macro_context=_MACRO_CONTEXT,
            declaration_resolver=resolver,
        )
