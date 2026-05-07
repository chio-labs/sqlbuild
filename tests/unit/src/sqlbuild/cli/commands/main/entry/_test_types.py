from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.cli.commands.main.helpers.compile.types import CompileLineageMode
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.compiler.discovery.exceptions import ProjectConfigError
from sqlbuild.compiler.lineage.types import ColumnLineageMode


@dataclass(frozen=True)
class MainTestCase:
    description: str
    argv: list[str]
    expected_exit_code: int
    expected_project_dir: Path | None = None
    expected_no_sql_validation: bool = False
    expected_full_refresh: bool = False
    expected_no_color: bool = False
    expected_debug: bool = False
    expected_manifest: bool = False
    expected_compile_lineage_mode: CompileLineageMode = CompileLineageMode.FAST
    expected_column_lineage_mode: ColumnLineageMode = ColumnLineageMode.RICH


@dataclass(frozen=True)
class MainErrorRenderingTestCase:
    description: str
    argv: list[str]
    error_type: type[CliUserError] | type[ProjectConfigError] | type[ValueError]
    error_factory: Callable[[Path], Exception]
    expected_stderr_fragment: str
    expected_exit_code: int
