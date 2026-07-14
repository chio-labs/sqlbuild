from pathlib import Path

from sqlbuild.compiler.compile._helpers.render.macros import load_project_macros
from sqlbuild.compiler.compile.models.core import LoadedMacro
from sqlbuild.compiler.compile.models.sql_tests import (
    CompiledDirectLogicSqlTestPayload,
    CompiledModelSqlTestPayload,
    CompiledSqlTest,
)
from sqlbuild.compiler.discovery.models import DiscoveredMacroFile


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


def compiled_sql_test_expected_model_names(test: CompiledSqlTest) -> tuple[str, ...]:
    if not isinstance(test.payload, CompiledModelSqlTestPayload):
        return ()
    return test.payload.expected_model_names


def compiled_sql_test_tested_resource_names(test: CompiledSqlTest) -> tuple[str, ...]:
    if not isinstance(test.payload, CompiledDirectLogicSqlTestPayload):
        return ()
    return test.payload.tested_resource_names
