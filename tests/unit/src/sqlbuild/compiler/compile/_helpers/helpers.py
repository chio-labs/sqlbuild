from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import cast

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile._helpers.render.macros import load_project_macros
from sqlbuild.compiler.compile.main._assemble_project import assemble_project
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import (
    CompileAdapterContext,
    CompileAnalysisSelection,
    CompiledDirectLogicSqlTestPayload,
    CompiledModel,
    CompiledModelSqlTestPayload,
    CompiledProject,
    CompiledSqlTest,
    CompileProjectInputs,
    DeclarationExpansionContext,
    DeclarationResolutionContext,
    LoadedMacro,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredMacroFile, DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.sql_values.types import CollectionRendering

DUCKDB_COMPILE_ADAPTER_CONTEXT: CompileAdapterContext = CompileAdapterContext(
    value_renderer=DuckDbAdapter(),
    collection_rendering=CollectionRendering.VALUE_LIST,
    python_functions_inherit_default_namespace=True,
)
DUCKDB_ARRAY_COMPILE_ADAPTER_CONTEXT: CompileAdapterContext = CompileAdapterContext(
    value_renderer=DUCKDB_COMPILE_ADAPTER_CONTEXT.value_renderer,
    collection_rendering=CollectionRendering.ARRAY,
    python_functions_inherit_default_namespace=True,
)
DUCKDB_DECLARATION_EXPANSION_CONTEXT: DeclarationExpansionContext = DeclarationExpansionContext(
    declarations=DeclarationResolutionContext(),
    value_renderer=DUCKDB_COMPILE_ADAPTER_CONTEXT.value_renderer,
    collection_rendering=DUCKDB_COMPILE_ADAPTER_CONTEXT.collection_rendering,
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
