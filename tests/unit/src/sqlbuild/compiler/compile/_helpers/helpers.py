import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import cast

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from sqlbuild.compiler.compile._helpers.attachment import core as attachment_core
from sqlbuild.compiler.compile._helpers.diagnostics.collector import (
    collect_compile_diagnostics,
)
from sqlbuild.compiler.compile._helpers.diagnostics.descriptions import (
    missing_description_diagnostics,
)
from sqlbuild.compiler.compile._helpers.render.macros import (
    expand_sql_macros,
    load_project_macros,
)
from sqlbuild.compiler.compile.classes.native_model_rendering import NativeModelRendering
from sqlbuild.compiler.compile.main._assemble_project import assemble_project
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import (
    AnalysisCacheContext,
    CompileAdapterContext,
    CompileAnalysisSelection,
    CompiledDirectLogicSqlTestPayload,
    CompiledLineageColumnFact,
    CompiledLineageSourceFact,
    CompiledModel,
    CompiledModelSqlTestPayload,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSqlTest,
    CompileModelInput,
    CompileProjectInputs,
    CompilerDiagnostic,
    CompileSeedInput,
    CompileSourceInput,
    CompileSqlFunctionInput,
    DeclarationExpansionContext,
    DeclarationResolutionContext,
    DeclarationRuntimeProjection,
    DeclarationScopeResolver,
    LoadedMacro,
    MacroContext,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, FunctionLanguage
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import (
    DiscoveredLoaderFunction,
    DiscoveredMacroFile,
    DiscoveredProjectInputs,
    DiscoveredProvider,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
    DiscoveredSqlFunctionFile,
    DiscoveredSqlHookFile,
    DiscoveredSqlModelFile,
    DiscoveredSqlScenarioFile,
    DiscoveredTaskFunction,
)
from sqlbuild.compiler.graph.main._build_lineage_upstream_deps import build_lineage_upstream_deps
from sqlbuild.compiler.lineage.types import ColumnLineageConfidence, ColumnTransformKind
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.compiler.planner._helpers.graph.core import build_execution_upstream_deps
from sqlbuild.compiler.planner._helpers.resolve.refs import resolve_ref_references
from sqlbuild.compiler.scopes.main.build_scope_lookup import build_scope_lookup
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    MacroMetadata,
    OwnershipRoot,
    ResourceIdentity,
    ResourceRecord,
    ScopeIndex,
    VisibilityRecord,
)
from sqlbuild.compiler.scopes.types import DeclarationKind, ResourceKind, ScopeKind
from sqlbuild.providers import Provider
from sqlbuild.spec.contracts.models import (
    LocalConfig,
    ProjectConfig,
    SchemaModelEntry,
    SchemaSeedEntry,
    SourceEntry,
)
from sqlbuild.sql_values.types import CollectionRendering

DUCKDB_COMPILE_ADAPTER_CONTEXT: CompileAdapterContext = CompileAdapterContext(
    value_renderer=DuckDbAdapter(),
    collection_rendering=CollectionRendering.VALUE_LIST,
    python_functions_inherit_default_namespace=True,
    sql_lexical_syntax=DuckDbAdapter.sql_lexical_syntax,
)
DUCKDB_ARRAY_COMPILE_ADAPTER_CONTEXT: CompileAdapterContext = CompileAdapterContext(
    value_renderer=DUCKDB_COMPILE_ADAPTER_CONTEXT.value_renderer,
    collection_rendering=CollectionRendering.ARRAY,
    python_functions_inherit_default_namespace=True,
    sql_lexical_syntax=DuckDbAdapter.sql_lexical_syntax,
)
DUCKDB_DECLARATION_EXPANSION_CONTEXT: DeclarationExpansionContext = DeclarationExpansionContext(
    declarations=DeclarationResolutionContext(),
    value_renderer=DUCKDB_COMPILE_ADAPTER_CONTEXT.value_renderer,
    collection_rendering=DUCKDB_COMPILE_ADAPTER_CONTEXT.collection_rendering,
)


def visible_declarations_without_runtime_values(
    *, enum_visibility: dict[str, tuple[VisibilityRecord, ...]] | None = None
) -> attachment_core._VisibleModelDeclarations:
    """Build declaration visibility facts without runtime declaration values."""

    return attachment_core._VisibleModelDeclarations(
        local_enums={},
        local_constants={},
        enums={},
        constants={},
        inaccessible_enums={},
        inaccessible_constants={},
        enum_visibility=enum_visibility or {},
        constant_visibility={},
        macros={},
        macro_records={},
        inaccessible_macros={},
    )


def direct_orders_lineage(*column_names: str) -> tuple[CompiledLineageColumnFact, ...]:
    return tuple(
        CompiledLineageColumnFact(
            output_column=column_name,
            upstream_columns=(
                CompiledLineageSourceFact(
                    resource_type=CompiledResourceType.MODEL,
                    resource_name="orders",
                    column_name=column_name,
                ),
            ),
            transform_kind=ColumnTransformKind.DIRECT,
            confidence=ColumnLineageConfidence.HIGH,
        )
        for column_name in column_names
    )


def build_scoped_macro_resolver(
    *, tmp_path: Path, definitions: dict[str, tuple[str, ScopeKind, str | None, str]]
) -> tuple[dict[str, LoadedMacro], DeclarationScopeResolver]:
    """Build loaded macros and canonical scope projection for expansion tests."""

    loaded: dict[str, LoadedMacro] = {}
    records: list[DeclarationRecord] = []
    projection: dict[DeclarationIdentity, LoadedMacro] = {}
    for name, (output, scope, owner, authored_path) in definitions.items():
        relative_path: Path = Path(authored_path)

        def macro(*, _output: str = output) -> str:
            return _output

        item: LoadedMacro = LoadedMacro(name, tmp_path / relative_path, relative_path, "", macro)
        identity: DeclarationIdentity = DeclarationIdentity(DeclarationKind.MACRO, name)
        loaded[name] = item
        projection[identity] = item
        records.append(
            DeclarationRecord(
                identity=identity,
                path=relative_path.as_posix(),
                line=1,
                column=1,
                scope=scope,
                ownership_root=OwnershipRoot(relative_path.parts[0]),
                owning_path=owner,
                macro=MacroMetadata(),
            )
        )
    model_identity: ResourceIdentity = ResourceIdentity(ResourceKind.MODEL, "orders")
    index: ScopeIndex = ScopeIndex(
        resources=(
            ResourceRecord(
                model_identity,
                "models/marts/finance/orders.sql",
                OwnershipRoot("models", resource_kind=ResourceKind.MODEL),
            ),
        ),
        declarations=tuple(records),
    )
    return loaded, DeclarationScopeResolver(
        project_dir=tmp_path,
        lookup=build_scope_lookup(index=index),
        projection=DeclarationRuntimeProjection(MappingProxyType(projection)),
    )


def build_loaded_macros(tmp_path: Path, macro_file_contents: str) -> dict[str, LoadedMacro]:
    macros_dir: Path = tmp_path / "macros"
    macros_dir.mkdir(parents=True, exist_ok=True)
    macro_file_path: Path = macros_dir / "common.py"
    macro_file_path.write_text(macro_file_contents, encoding="utf-8")
    return load_project_macros(
        (
            DiscoveredMacroFile(
                file_path=macro_file_path,
                relative_path=Path("macros/common.py"),
                contents=macro_file_contents,
            ),
        )
    )


def compile_first_model(*, project_dir: Path) -> CompiledModel:
    """Compile a fixture project and return its first model."""

    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    compile_inputs: CompileProjectInputs = build_compile_inputs(
        discovered_inputs=discovered_inputs,
        adapter_context=DUCKDB_COMPILE_ADAPTER_CONTEXT,
        run_id="test_run",
    )
    compiled_project: CompiledProject = assemble_project(
        inputs=compile_inputs,
        skip_column_inference=True,
    )
    return compiled_project.models[0]


def compile_project_inputs(*, project_dir: Path) -> CompileProjectInputs:
    """Compile a discovered DuckDB fixture through the input attachment boundary."""

    return build_compile_inputs(
        discovered_inputs=discover_project_inputs(project_dir=project_dir),
        adapter_context=DUCKDB_COMPILE_ADAPTER_CONTEXT,
        run_id="test_run",
    )


def compile_project_with_cache(
    *,
    project_dir: Path,
    analysis_selection: CompileAnalysisSelection | None = None,
    no_cache: bool = False,
) -> CompiledProject:
    """Compile a discovered DuckDB fixture through the cache-enabled project boundary."""

    effective_selection: CompileAnalysisSelection = replace(
        analysis_selection or CompileAnalysisSelection(),
        no_cache=no_cache,
    )
    return build_compiled_project(
        discovered_inputs=discover_project_inputs(project_dir=project_dir),
        adapter=DuckDbAdapter(),
        analysis_selection=effective_selection,
    )


def compiled_sql_test_expected_model_names(test: CompiledSqlTest) -> tuple[str, ...]:
    getters: MappingProxyType[type[object], Callable[[object], tuple[str, ...]]] = MappingProxyType(
        {
            CompiledModelSqlTestPayload: _compiled_model_expected_names,
            CompiledDirectLogicSqlTestPayload: _compiled_direct_empty_names,
        }
    )
    return getters[type(test.payload)](test.payload)


def compiled_sql_test_tested_resource_names(test: CompiledSqlTest) -> tuple[str, ...]:
    getters: MappingProxyType[type[object], Callable[[object], tuple[str, ...]]] = MappingProxyType(
        {
            CompiledModelSqlTestPayload: _compiled_model_empty_names,
            CompiledDirectLogicSqlTestPayload: _compiled_direct_tested_names,
        }
    )
    return getters[type(test.payload)](test.payload)


def _compiled_model_expected_names(payload: object) -> tuple[str, ...]:
    return cast(CompiledModelSqlTestPayload, payload).expected_model_names


def _compiled_direct_empty_names(payload: object) -> tuple[str, ...]:
    del payload
    return ()


def _compiled_model_empty_names(payload: object) -> tuple[str, ...]:
    del payload
    return ()


def _compiled_direct_tested_names(payload: object) -> tuple[str, ...]:
    return cast(CompiledDirectLogicSqlTestPayload, payload).tested_resource_names


def singular_audit_files(*, base: dict[str, str], sql: str) -> dict[str, str]:
    """Return project files with one top-level singular audit over the given SQL."""

    return base | {"audits/singular/check.sql": f"AUDIT ();\n{sql}"}


def model_header(*, key: str, value: str) -> str:
    """Return a one-column model whose header sets one key."""

    return f"MODEL (description 'Test model check.', {key} {value});\nSELECT 1 AS order_id"


def compile_and_assemble(*, project_dir: Path) -> CompiledProject:
    """Attach and assemble a DuckDB fixture so scope placement is validated."""

    return assemble_project(
        inputs=compile_project_inputs(project_dir=project_dir), skip_column_inference=True
    )


def gate_audit(*, read: str) -> str:
    """Return a generic audit that joins its target to another resource."""

    return f"AUDIT ();\nSELECT s.* FROM @relation s LEFT JOIN {read} a USING (code)"


def gate_model(*, sql: str, header: str = "MODEL (description 'Test model.');") -> str:
    """Return a model with the given header."""

    return f"{header}\n{sql}"


def execution_edge_names(*, project: CompiledProject) -> frozenset[tuple[str, str]]:
    """Return (node, upstream) name pairs of the project's execution graph."""

    edges: set[tuple[str, str]] = set()
    key: CompiledObjectKey
    deps: tuple[CompiledObjectKey, ...]
    for key, deps in build_execution_upstream_deps(project).items():
        edges.update((key.name, dep.name) for dep in deps)
    return frozenset(edges)


def inline_sql_hook_header(sql: str) -> str:
    """Return a MODEL header running one inline SQL pre-hook."""

    return f"MODEL (description 'Test model.', pre_hooks [inline_sql('{sql}')]);"


def lineage_edge_names(*, project: CompiledProject) -> frozenset[tuple[str, str]]:
    """Return (node, upstream) name pairs of the project's lineage graph used for selection."""

    edges: set[tuple[str, str]] = set()
    key: CompiledObjectKey
    deps: tuple[CompiledObjectKey, ...]
    for key, deps in build_lineage_upstream_deps(project).items():
        edges.update((key.name, dep.name) for dep in deps)
    return frozenset(edges)


def expand_typed_macro_sql(
    *, tmp_path: Path, macro_file_contents: str, sql: str, enforce_explicit: bool = True
) -> str:
    """Expand model SQL for the ``order_summary`` model against one macro module."""

    loaded_macros: dict[str, LoadedMacro] = build_loaded_macros(tmp_path, macro_file_contents)
    return expand_sql_macros(
        sql=sql,
        file_path=tmp_path / "models" / "order_summary.sql",
        loaded_macros=loaded_macros,
        macro_context=MacroContext(
            adapter_name="duckdb",
            sql_analysis_enabled=True,
            target_name="dev",
            _enforce_explicit_references=enforce_explicit,
        ),
        consumer=ResourceIdentity(kind=ResourceKind.MODEL, name="order_summary"),
    )


def resolve_model_references_for_adapter(*, sql: str, adapter_name: str) -> str:
    """Resolve ``__ref("orders")`` to ``analytics.sales.orders`` with one adapter's quoting."""

    adapters: dict[str, Callable[[], BaseAdapter]] = {
        "bigquery": BigQueryAdapter,
        "duckdb": DuckDbAdapter,
        "postgres": PostgresAdapter,
        "snowflake": SnowflakeAdapter,
        "sqlserver": SqlServerAdapter,
    }
    return resolve_ref_references(
        query_sql=sql,
        model_locations={
            "orders": CompiledRelationLocation(
                database="analytics", schema="sales", name="orders", qualified_name=None
            )
        },
        seed_locations={},
        cursor_bounds=None,
        cursor_filter_inputs={},
        adapter=adapters[adapter_name](),
        cursor_type=None,
        lower_bound_inclusive=True,
    )


def python_hook_source(*, reads: str = "()", body: str = "    return None\n") -> str:
    """Return a Python hook module defining ``refresh_lookup`` with declared reads."""

    return (
        "from sqlbuild.hooks import hook\n"
        "from sqlbuild.refs import model, seed, source\n\n\n"
        f"@hook(reads={reads})\n"
        "def refresh_lookup(ctx):\n"
        f"{body}"
    )


def python_task_source(*, body: str) -> str:
    """Return a Python task module defining ``export_orders`` that depends on ``orders``."""

    return (
        "from sqlbuild.refs import model\n"
        "from sqlbuild.tasks import task\n\n\n"
        '@task(depends_on=model("orders"))\n'
        "def export_orders(ctx):\n"
        f"{body}"
    )


def python_check_source(*, depends_on: str, body: str) -> str:
    """Return a Python check module defining ``orders_present`` with the given dependencies."""

    return (
        "from sqlbuild.checks import check\n"
        "from sqlbuild.refs import model\n\n\n"
        f"@check(depends_on={depends_on})\n"
        "def orders_present(ctx):\n"
        f"{body}"
        "    return ctx.pass_()\n"
    )


def python_loader_source(*, depends_on: str, body: str) -> str:
    """Return loaders ``raw_regions`` and ``raw_customers``; the latter runs ``body``."""

    return (
        "from sqlbuild.loaders import loader\n\n\n"
        "@loader\n"
        "def raw_regions(ctx):\n"
        "    '''Test loader raw_regions.'''\n    return [{'id': 1}]\n\n\n"
        f"@loader(depends_on=[{depends_on}])\n"
        "def raw_customers(ctx):\n"
        f"{body}"
        "    return [{'id': 1}]\n"
    )


def collect_typed_macro_violations(
    *, tmp_path: Path, macro_file_contents: str, sql: str
) -> tuple[CompilerDiagnostic, ...]:
    """Expand ``order_summary`` SQL and return the explicit-reference violations it reports."""

    with collect_compile_diagnostics() as violations:
        expand_typed_macro_sql(tmp_path=tmp_path, macro_file_contents=macro_file_contents, sql=sql)
    return violations.diagnostics


def render_compile_diagnostics(*, project: CompiledProject) -> str:
    """Render every project diagnostic with its code, message, location, and help."""

    return "\n".join(
        f"[{diagnostic.code}] {diagnostic.message} --> {diagnostic.path}:{diagnostic.line} "
        f"= help: {diagnostic.help}"
        for diagnostic in project.diagnostics
    )


def write_scoped_macro_orders_project(project_dir: Path) -> None:
    """Write a project with one global macro and one test-scoped macro."""

    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model: Path = project_dir / "models" / "orders.sql"
    model.parent.mkdir(parents=True)
    model.write_text(
        'MODEL (description "Orders");\nSELECT 1 AS order_id WHERE @order_filter("1")\n',
        encoding="utf-8",
    )
    (project_dir / "macros").mkdir()
    (project_dir / "macros" / "order_filter.py").write_text(
        'def order_filter(column: str) -> str:\n    return f"{column} > 0"\n', encoding="utf-8"
    )
    tests_dir: Path = project_dir / "tests" / "unit"
    (tests_dir / "_macros").mkdir(parents=True)
    (tests_dir / "_macros" / "row_limit.py").write_text(
        'def row_limit() -> str:\n    return "LIMIT 1"\n', encoding="utf-8"
    )
    (tests_dir / "test_orders.sql").write_text(
        "TEST ();\nWITH\n__ref__orders AS (SELECT 1 AS order_id),\n"
        "__expected__orders AS (SELECT order_id FROM __ref__orders @row_limit())\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def stored_analysis_contents(*, context: AnalysisCacheContext, cache_key: str) -> str:
    """Return the raw stored payload of one analysis cache entry."""

    database_path: Path = next(context.root.rglob("model-analysis.sqlite3"))
    with sqlite3.connect(database_path) as connection:
        row: tuple[str] = connection.execute(
            "SELECT payload FROM model_analysis WHERE cache_key = ?", (cache_key,)
        ).fetchone()
    return row[0]


REQUIRED_DESCRIPTION_BASE_INPUTS: DiscoveredProjectInputs = DiscoveredProjectInputs(
    project_config=ProjectConfig(name="orders", adapter="duckdb"),
    local_config=LocalConfig(),
)


@dataclass(frozen=True)
class RequiredDescriptionInputs:
    """Compile inputs passed to the required-description check."""

    discovered_inputs: DiscoveredProjectInputs = REQUIRED_DESCRIPTION_BASE_INPUTS
    model_inputs: tuple[CompileModelInput, ...] = ()
    seed_inputs: tuple[CompileSeedInput, ...] = ()
    source_inputs: tuple[CompileSourceInput, ...] = ()
    function_inputs: tuple[CompileSqlFunctionInput, ...] = ()


class OrdersApi(Provider):
    """Client for the orders API."""


class UndescribedApi(Provider):
    pass


_PROVIDER_CLASS_BY_UNDESCRIBED: dict[bool, type[Provider]] = {
    False: OrdersApi,
    True: UndescribedApi,
}


def refresh_exports_task(ctx: object) -> None:
    del ctx


def documented_returns_loader(ctx: object) -> None:
    """Returned orders from the support desk."""

    del ctx


def model_description_inputs(
    description: str | None,
    *,
    contents: str = "-- totals\nMODEL (materialized table);\nSELECT 1 AS id\n",
) -> RequiredDescriptionInputs:
    return RequiredDescriptionInputs(
        model_inputs=(
            CompileModelInput(
                model_file=DiscoveredSqlModelFile(
                    file_path=Path("/project/models/order_totals.sql"),
                    relative_path=Path("models/order_totals.sql"),
                    contents=contents,
                    header_values={},
                    header_column_locations={},
                    output_column_locations={},
                    query_sql="SELECT 1 AS id",
                ),
                schema_entry=SchemaModelEntry(name="order_totals", description=description),
            ),
        )
    )


def scenario_description_inputs(
    description: str | None, *, contents: str = "\nSCENARIO ();\nSELECT 1\n"
) -> RequiredDescriptionInputs:
    return RequiredDescriptionInputs(
        discovered_inputs=replace(
            REQUIRED_DESCRIPTION_BASE_INPUTS,
            scenario_files=(
                DiscoveredSqlScenarioFile(
                    file_path=Path("/project/tests/scenarios/orders__paid.sql"),
                    relative_path=Path("tests/scenarios/orders__paid.sql"),
                    contents=contents,
                    header_values={"description": description},
                    sql_body="SELECT 1",
                    name="orders__paid",
                ),
            ),
        )
    )


def seed_description_inputs(description: str | None) -> RequiredDescriptionInputs:
    contents: str = "seeds:\n  - name: product_types\n"
    return RequiredDescriptionInputs(
        seed_inputs=(
            CompileSeedInput(
                seed_file=DiscoveredSeedFile(
                    file_path=Path("/project/seeds/product_types.csv"),
                    relative_path=Path("seeds/product_types.csv"),
                ),
                schema_entry=SchemaSeedEntry(name="product_types", description=description),
                schema_file=DiscoveredSchemaFile(
                    file_path=Path("/project/seeds/product_types.yml"),
                    relative_path=Path("seeds/product_types.yml"),
                    contents=contents,
                    model_entries=(),
                    seed_entries=(),
                ),
            ),
        )
    )


def returns_source_input(*, description: str | None, loader: str | None) -> CompileSourceInput:
    return CompileSourceInput(
        source_entry=SourceEntry(name="raw_returns", description=description, loader=loader),
        source_file=DiscoveredSourceFile(
            file_path=Path("/project/sources/raw.yml"),
            relative_path=Path("sources/raw.yml"),
            contents="sources:\n  - name: raw_orders\n    description: Orders\n"
            "  - name: raw_returns\n",
            source_entries=(),
        ),
    )


def source_description_inputs(description: str | None) -> RequiredDescriptionInputs:
    return RequiredDescriptionInputs(
        source_inputs=(returns_source_input(description=description, loader=None),)
    )


def returns_loader(description: str | None) -> DiscoveredLoaderFunction:
    return DiscoveredLoaderFunction(
        file_path=Path("/project/python/loaders/raw_returns.py"),
        relative_path=Path("python/loaders/raw_returns.py"),
        name="raw_returns",
        function=documented_returns_loader,
        description=description,
    )


def loader_backed_source_description_inputs(description: str | None) -> RequiredDescriptionInputs:
    return RequiredDescriptionInputs(
        source_inputs=(returns_source_input(description=None, loader="raw_returns"),),
        discovered_inputs=replace(
            REQUIRED_DESCRIPTION_BASE_INPUTS, loader_functions=(returns_loader(description),)
        ),
    )


def loader_only_description_inputs(description: str | None) -> RequiredDescriptionInputs:
    return RequiredDescriptionInputs(
        discovered_inputs=replace(
            REQUIRED_DESCRIPTION_BASE_INPUTS, loader_functions=(returns_loader(description),)
        )
    )


def function_description_inputs(
    description: str | None,
    *,
    contents: str = "FUNCTION (returns BOOLEAN);\n\nTRUE\n",
    relative_path: Path = Path("functions/sql/is_large_order.sql"),
    language: FunctionLanguage = FunctionLanguage.SQL,
) -> RequiredDescriptionInputs:
    return RequiredDescriptionInputs(
        function_inputs=(
            CompileSqlFunctionInput(
                function_file=DiscoveredSqlFunctionFile(
                    file_path=Path("/project") / relative_path,
                    relative_path=relative_path,
                    contents=contents,
                    header_values={},
                    body_sql="TRUE",
                ),
                name="is_large_order",
                arguments=(),
                returns="BOOLEAN",
                body_sql="TRUE",
                description=description,
                language=language,
            ),
        )
    )


def sql_hook_description_inputs(
    description: str | None, *, contents: str = "HOOK ();\nSELECT 1\n"
) -> RequiredDescriptionInputs:
    return RequiredDescriptionInputs(
        discovered_inputs=replace(
            REQUIRED_DESCRIPTION_BASE_INPUTS,
            sql_hook_files=(
                DiscoveredSqlHookFile(
                    file_path=Path("/project/hooks/sql/analyze_orders.sql"),
                    relative_path=Path("hooks/sql/analyze_orders.sql"),
                    contents=contents,
                    header_values={},
                    sql_body="SELECT 1",
                    name="analyze_orders",
                    description=description,
                ),
            ),
        )
    )


def task_description_inputs(description: str | None) -> RequiredDescriptionInputs:
    return RequiredDescriptionInputs(
        discovered_inputs=replace(
            REQUIRED_DESCRIPTION_BASE_INPUTS,
            task_functions=(
                DiscoveredTaskFunction(
                    file_path=Path("/project/python/tasks/refresh_exports.py"),
                    relative_path=Path("python/tasks/refresh_exports.py"),
                    name="refresh_exports",
                    function=refresh_exports_task,
                    description=description,
                ),
            ),
        )
    )


def provider_description_inputs(description: str | None) -> RequiredDescriptionInputs:
    provider_class: type[Provider] = _PROVIDER_CLASS_BY_UNDESCRIBED[description is None]
    return RequiredDescriptionInputs(
        discovered_inputs=replace(
            REQUIRED_DESCRIPTION_BASE_INPUTS,
            providers=(
                DiscoveredProvider(
                    file_path=Path("/project/providers/orders_api.py"),
                    relative_path=Path("providers/orders_api.py"),
                    name="orders_api",
                    provider_class=provider_class,
                    settings=provider_class(),
                ),
            ),
        )
    )


def required_description_diagnostics(
    inputs: RequiredDescriptionInputs,
) -> tuple[CompilerDiagnostic, ...]:
    return missing_description_diagnostics(
        discovered_inputs=inputs.discovered_inputs,
        model_inputs=inputs.model_inputs,
        seed_inputs=inputs.seed_inputs,
        source_inputs=inputs.source_inputs,
        function_inputs=inputs.function_inputs,
    )


def scan_references_with_python(monkeypatch: pytest.MonkeyPatch) -> None:
    """Send every model reference scan through the cached Python extractor."""

    monkeypatch.setattr(NativeModelRendering, "model_references", lambda self, **kwargs: None)
