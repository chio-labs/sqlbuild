"""SQL-native test compile and compiled models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.compiler.compile.constants import DEFAULT_SQL_TEST_MODE
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.discovery.models import DiscoveredSqlTestBlock, DiscoveredSqlTestFile


@dataclass(frozen=True)
class CompileSqlTestCte:
    """One top-level SQL-native test CTE extracted after macro expansion."""

    name: str
    sql_body: str


@dataclass(frozen=True)
class CompileModelSqlTestCtes:
    """Extracted model-mode SQL-native test CTE semantics."""

    authored_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    macro_mocks: dict[str, str] = field(default_factory=dict)
    mock_model_names: tuple[str, ...] = field(default_factory=tuple)
    mock_source_names: tuple[str, ...] = field(default_factory=tuple)
    mock_seed_names: tuple[str, ...] = field(default_factory=tuple)
    mock_dbt_ref_names: tuple[str, ...] = field(default_factory=tuple)
    expected_model_names: tuple[str, ...] = field(default_factory=tuple)
    assertion_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    assertion_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompileDirectLogicSqlTestCtes:
    """Extracted direct-logic SQL-native test CTE semantics."""

    mode: SqlTestMode
    helper_ctes: tuple[CompileSqlTestCte, ...]
    actual_cte: CompileSqlTestCte
    expected_cte: CompileSqlTestCte


type CompileSqlTestCtesPayload = CompileModelSqlTestCtes | CompileDirectLogicSqlTestCtes


@dataclass(frozen=True)
class CompileSqlTestCtes:
    """Extracted top-level SQL-native test CTE semantics."""

    mode: SqlTestMode
    payload: CompileSqlTestCtesPayload


@dataclass(frozen=True)
class CompileModelSqlTestInputPayload:
    """Model-mode SQL test compile payload."""

    authored_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    macro_mocks: dict[str, str] = field(default_factory=dict)
    mock_model_names: tuple[str, ...] = field(default_factory=tuple)
    mock_source_names: tuple[str, ...] = field(default_factory=tuple)
    mock_seed_names: tuple[str, ...] = field(default_factory=tuple)
    mock_dbt_ref_names: tuple[str, ...] = field(default_factory=tuple)
    expected_model_names: tuple[str, ...] = field(default_factory=tuple)
    assertion_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    assertion_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompileDirectLogicSqlTestInputPayload:
    """Direct-logic SQL test compile payload."""

    actual_cte: CompileSqlTestCte
    expected_cte: CompileSqlTestCte
    mode: SqlTestMode
    helper_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    tested_resource_names: tuple[str, ...] = field(default_factory=tuple)


type CompileSqlTestInputPayload = (
    CompileModelSqlTestInputPayload | CompileDirectLogicSqlTestInputPayload
)


@dataclass(frozen=True)
class CompileSqlTestInput:
    """One discovered SQL-native test block with compile-time SQL expansion applied."""

    test_file: DiscoveredSqlTestFile
    test_block: DiscoveredSqlTestBlock
    sql_body: str
    mode: SqlTestMode = DEFAULT_SQL_TEST_MODE
    payload: CompileSqlTestInputPayload = field(default_factory=CompileModelSqlTestInputPayload)


@dataclass(frozen=True)
class CompiledModelSqlTestPayload:
    """Compiled model-mode SQL test payload."""

    authored_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    macro_mocks: dict[str, str] = field(default_factory=dict)
    model_query_overrides: dict[str, str] = field(default_factory=dict)
    mock_model_names: tuple[str, ...] = field(default_factory=tuple)
    mock_source_names: tuple[str, ...] = field(default_factory=tuple)
    mock_seed_names: tuple[str, ...] = field(default_factory=tuple)
    mock_dbt_ref_names: tuple[str, ...] = field(default_factory=tuple)
    expected_model_names: tuple[str, ...] = field(default_factory=tuple)
    assertion_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    assertion_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompiledDirectLogicSqlTestPayload:
    """Compiled direct-logic SQL test payload."""

    actual_cte: CompileSqlTestCte
    expected_cte: CompileSqlTestCte
    mode: SqlTestMode = DEFAULT_SQL_TEST_MODE
    helper_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    tested_resource_names: tuple[str, ...] = field(default_factory=tuple)


type CompiledSqlTestPayload = CompiledModelSqlTestPayload | CompiledDirectLogicSqlTestPayload


@dataclass(frozen=True)
class CompiledSqlTest:
    """Compiled SQL-native unit test metadata selected by expected targets."""

    key: CompiledObjectKey
    scope_deps: tuple[CompiledObjectKey, ...]
    name: str
    test_file: DiscoveredSqlTestFile
    test_block: DiscoveredSqlTestBlock
    sql_body: str
    mode: SqlTestMode = DEFAULT_SQL_TEST_MODE
    payload: CompiledSqlTestPayload = field(default_factory=CompiledModelSqlTestPayload)
