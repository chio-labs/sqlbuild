from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
from typing import cast

from sqlbuild.compiler.compile._helpers.render.macros import load_project_macros
from sqlbuild.compiler.compile.main._assemble_project import assemble_project
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import (
    CompiledDirectLogicSqlTestPayload,
    CompiledModel,
    CompiledModelSqlTestPayload,
    CompiledProject,
    CompiledSqlTest,
    CompileProjectInputs,
    LoadedMacro,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredMacroFile, DiscoveredProjectInputs


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
        run_id="test_run",
    )
    compiled_project: CompiledProject = assemble_project(
        inputs=compile_inputs,
        skip_column_inference=True,
    )
    return compiled_project.models[0]


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
