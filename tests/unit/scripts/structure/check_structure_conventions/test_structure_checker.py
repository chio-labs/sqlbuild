from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from textwrap import dedent

import pytest

from scripts.structure.check_structure_conventions import main
from tests.unit.scripts.structure.check_structure_conventions._test_types import (
    CheckCliMainTestCase,
    CheckPathsTestCase,
)
from tests.unit.scripts.structure.check_structure_conventions.helpers import (
    collect_violation_codes,
    compliant_repo_files,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CheckPathsTestCase(
            description="reports no violations for a compliant repo slice",
            repo_files=compliant_repo_files(),
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="reports relative import usage",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                from .models import ExampleModel


                def load_example() -> ExampleModel:
                    return ExampleModel(name="demo")
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC001",),
        ),
        CheckPathsTestCase(
            description="reports raw color helper import outside style layer",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                from sqlbuild.shared.helpers.output.colors import green_bold, supports_color


                def load_example() -> str:
                    return green_bold(str(supports_color()))
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC041",),
        ),
        CheckPathsTestCase(
            description="allows supports color helper import",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                from sqlbuild.shared.helpers.output.colors import supports_color


                def load_example() -> bool:
                    return supports_color()
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="reports singular source freshness writer usage",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                from sqlbuild.compiler.source_freshness.main.write import (
                    write_source_freshness_record,
                )


                def load_example() -> None:
                    write_source_freshness_record()
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC057", "SC057"),
        ),
        CheckPathsTestCase(
            description="reports source freshness insert sql outside adapters",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                from sqlbuild.compiler.source_freshness.constants import SOURCE_FRESHNESS_TABLE_NAME


                def load_example() -> str:
                    return f"INSERT INTO {SOURCE_FRESHNESS_TABLE_NAME} VALUES (1)"
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC058",),
        ),
        CheckPathsTestCase(
            description="reports internal pure re-export module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/bridge.py": dedent(
                    """
                from __future__ import annotations

                from sqlbuild.shared.models import RetryPolicy

                __all__ = ("RetryPolicy",)
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC046", "SC047"),
        ),
        CheckPathsTestCase(
            description="allows top-level public re-export module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/retries.py": dedent(
                    """
                from sqlbuild.shared.models import RetryPolicy

                __all__ = ("RetryPolicy",)
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="does not report pure re-export violation for integration public surface",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/integrations/example/__init__.py": dedent(
                    """
                from __future__ import annotations

                from sqlbuild.shared.models import RetryPolicy

                __all__ = ["RetryPolicy"]
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC006",),
        ),
        CheckPathsTestCase(
            description="reports internal helper __all__ export surface",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/formatting.py": dedent(
                    """
                from sqlbuild.shared.models import RetryPolicy

                __all__ = ("RetryPolicy", "format_name")


                def format_name(name: str) -> str:
                    return name.strip()
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC047",),
        ),
        CheckPathsTestCase(
            description="reports oversized source file outside allowlisted boundaries",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/constants.py": "DEFAULT_NAME = 'demo'\n" * 2001,
            },
            expected_violation_codes=("SC048",),
        ),
        CheckPathsTestCase(
            description="allows oversized scripts file",
            repo_files=compliant_repo_files()
            | {
                "scripts/example_tool/constants.py": "EXIT_CODE = 0\n" * 2001,
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="allows oversized adapter client source file",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/adapters/example/client.py": "class ExampleAdapter:\n    pass\n"
                + "    FILLER = 'implementation detail'\n" * 2000,
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="allows oversized virtual state backend source file",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/virtual/state/classes/example.py": "class ExampleState:\n    pass\n"
                + "    FILLER = 'implementation detail'\n" * 2000,
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="reports mixed flat helper modules and concern subfolders",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/__init__.py": '"""Helpers."""\n',
                "src/sqlbuild/example/widget/helpers/build.py": (
                    "def build() -> str:\n    return 'demo'\n"
                ),
                "src/sqlbuild/example/widget/helpers/render/name.py": (
                    "def render() -> str:\n    return 'demo'\n"
                ),
            },
            expected_violation_codes=("SC049",),
        ),
        CheckPathsTestCase(
            description="reports mixed helper layout without init module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/build.py": (
                    "def build() -> str:\n    return 'demo'\n"
                ),
                "src/sqlbuild/example/widget/helpers/render/name.py": (
                    "def render() -> str:\n    return 'demo'\n"
                ),
            },
            expected_violation_codes=("SC049",),
        ),
        CheckPathsTestCase(
            description="reports shared subfolder mixed with flat helper modules",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/__init__.py": '"""Helpers."""\n',
                "src/sqlbuild/example/widget/helpers/build.py": (
                    "def build() -> str:\n    return 'demo'\n"
                ),
                "src/sqlbuild/example/widget/helpers/shared/name.py": (
                    "def render() -> str:\n    return 'demo'\n"
                ),
            },
            expected_violation_codes=("SC049",),
        ),
        CheckPathsTestCase(
            description="allows shared subfolder when helpers are fully subfoldered",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/__init__.py": '"""Helpers."""\n',
                "src/sqlbuild/example/widget/helpers/build/core.py": (
                    "def build() -> str:\n    return 'demo'\n"
                ),
                "src/sqlbuild/example/widget/helpers/shared/name.py": (
                    "def render() -> str:\n    return 'demo'\n"
                ),
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="reports helpers package with too many flat modules",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/__init__.py": '"""Helpers."""\n',
                **{
                    f"src/sqlbuild/example/widget/helpers/module_{index}.py": (
                        f"def build_{index}() -> int:\n    return {index}\n"
                    )
                    for index in range(11)
                },
            },
            expected_violation_codes=("SC050",),
        ),
        CheckPathsTestCase(
            description="reports helpers package without init module with too many flat modules",
            repo_files=compliant_repo_files()
            | {
                **{
                    f"src/sqlbuild/example/widget/helpers/module_{index}.py": (
                        f"def build_{index}() -> int:\n    return {index}\n"
                    )
                    for index in range(11)
                },
            },
            expected_violation_codes=("SC050",),
        ),
        CheckPathsTestCase(
            description="reports mixed flat main modules and concern subfolders",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/__init__.py": '"""Entrypoints."""\n',
                "src/sqlbuild/example/widget/main/build.py": (
                    "def build() -> str:\n    return 'demo'\n"
                ),
                "src/sqlbuild/example/widget/main/render/name.py": (
                    "def render() -> str:\n    return 'demo'\n"
                ),
            },
            expected_violation_codes=("SC059",),
        ),
        CheckPathsTestCase(
            description="reports main package support folders outside CLI commands",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/__init__.py": '"""Entrypoints."""\n',
                "src/sqlbuild/example/widget/main/shared/__init__.py": '"""Shared."""\n',
            },
            expected_violation_codes=("SC061",),
        ),
        CheckPathsTestCase(
            description="reports CLI command main support folders",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/cli/commands/main/__init__.py": '"""Entrypoints."""\n',
                "src/sqlbuild/cli/commands/main/shared/__init__.py": '"""Shared."""\n',
            },
            expected_violation_codes=("SC061",),
        ),
        CheckPathsTestCase(
            description="reports main package with too many flat modules",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/__init__.py": '"""Entrypoints."""\n',
                **{
                    f"src/sqlbuild/example/widget/main/module_{index}.py": (
                        f"def build_{index}() -> int:\n    return {index}\n"
                    )
                    for index in range(21)
                },
            },
            expected_violation_codes=("SC060",),
        ),
        CheckPathsTestCase(
            description="reports ambiguous target reuse source terminology",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/compiler/planner/helpers/standard_reuse_example.py": (
                    "def build_origin() -> str:\n"
                    "    source"
                    '_relation = "prod.orders"\n'
                    "    return source"
                    "_relation\n"
                )
            },
            expected_violation_codes=("SC045", "SC045"),
        ),
        CheckPathsTestCase(
            description="reports ambiguous dbt reuse source terminology",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/integrations/dbt/helpers/reuse_candidates.py": (
                    "def build_origin() -> str:\n"
                    "    source_relation = 'prod.orders'\n"
                    "    return source_relation\n"
                )
            },
            expected_violation_codes=("SC045", "SC045"),
        ),
        CheckPathsTestCase(
            description="reports globally banned reuse source terminology",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/planning.py": (
                    "def build_origin() -> str:\n"
                    "    source_fingerprint = 'abc'\n"
                    "    return source_fingerprint\n"
                )
            },
            expected_violation_codes=("SC045", "SC045"),
        ),
        CheckPathsTestCase(
            description="reports ambiguous clone source target terminology",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/executor/clone/main/example.py": (
                    "def run_clone(source_target_name: str) -> str:\n"
                    "    source_connection = source_target_name\n"
                    "    return source_connection\n"
                )
            },
            expected_violation_codes=("SC045", "SC045", "SC045", "SC045"),
        ),
        CheckPathsTestCase(
            description="allows source target terminology in source deferral logic",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/compiler/planner/helpers/warehouse/source_deferral.py": (
                    "def resolve() -> str | None:\n"
                    "    source_target_name = 'prod'\n"
                    "    return source_target_name\n"
                )
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="allows source connection terminology in virtual source logic",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/virtual/planner/main/plan.py": (
                    "def resolve(connection: object) -> object:\n"
                    "    source_connection = connection\n"
                    "    return source_connection\n"
                )
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="allows real adapter source relation terminology outside reuse modules",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/planning.py": (
                    "def render(source_relation: str) -> str:\n    return source_relation\n"
                )
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="reports flat runtime main module under nested package",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main.py": dedent(
                    """
                def load_example() -> str:
                    return "demo"
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC027",),
        ),
        CheckPathsTestCase(
            description="reports obvious dev tooling under src package",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/testing/check_example.py": dedent(
                    """
                def main() -> int:
                    return 0
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC002", "SC027"),
        ),
        CheckPathsTestCase(
            description="reports top-level role file under runtime domain",
            repo_files=compliant_repo_files()
            | {"src/sqlbuild/example/models.py": "class Example: ...\n"},
            expected_violation_codes=("SC017", "SC008"),
        ),
        CheckPathsTestCase(
            description="reports top-level direct module under runtime domain",
            repo_files=compliant_repo_files() | {"src/sqlbuild/example/compile.py": "value = 1\n"},
            expected_violation_codes=("SC018",),
        ),
        CheckPathsTestCase(
            description="reports top-level helpers package under runtime domain",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/helpers/__init__.py": '"""Helpers."""\n',
                "src/sqlbuild/example/helpers/build.py": "def build() -> str:\n    return 'demo'\n",
            },
            expected_violation_codes=("SC017",),
        ),
        CheckPathsTestCase(
            description="reports banned generic filename",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/common.py": dedent(
                    """
                def build_name() -> str:
                    return "demo"
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC003", "SC027"),
        ),
        CheckPathsTestCase(
            description="reports helpers module file",
            repo_files=compliant_repo_files()
            | {"src/sqlbuild/example/widget/helpers.py": "value = 1\n"},
            expected_violation_codes=("SC003", "SC004"),
        ),
        CheckPathsTestCase(
            description="reports classes module file",
            repo_files=compliant_repo_files()
            | {"src/sqlbuild/example/widget/classes.py": "class Example: ...\n"},
            expected_violation_codes=("SC005", "SC027"),
        ),
        CheckPathsTestCase(
            description="reports multiple classes in classes package module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/classes/session.py": dedent(
                    """
                class ExampleSession:
                    pass


                class ExampleContainer:
                    pass
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC043",),
        ),
        CheckPathsTestCase(
            description="reports non-minimal init module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/__init__.py": dedent(
                    """
                from sqlbuild.example.widget.main import load_example
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC006",),
        ),
        CheckPathsTestCase(
            description="reports dataclass in types module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/types.py": dedent(
                    """
                from dataclasses import dataclass


                @dataclass(frozen=True)
                class ExampleType:
                    name: str
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC007", "SC014"),
        ),
        CheckPathsTestCase(
            description="reports enum in models module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/models.py": dedent(
                    """
                from enum import Enum


                class ExampleModel(Enum):
                    BASIC = "basic"
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC008", "SC015"),
        ),
        CheckPathsTestCase(
            description="reports function in constants module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/constants.py": dedent(
                    """
                def default_name() -> str:
                    return "demo"
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC009",),
        ),
        CheckPathsTestCase(
            description="reports dataclass outside models module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/view.py": dedent(
                    """
                from dataclasses import dataclass


                @dataclass(frozen=True)
                class ExampleModel:
                    name: str
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC027", "SC014"),
        ),
        CheckPathsTestCase(
            description="reports enum outside types module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/view.py": dedent(
                    """
                from enum import Enum


                class ExampleKind(Enum):
                    BASIC = "basic"
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC027", "SC015"),
        ),
        CheckPathsTestCase(
            description="allows private enum inside helpers module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/worker.py": dedent(
                    """
                from enum import StrEnum


                class _WorkerKind(StrEnum):
                    BASIC = "basic"


                def run_worker() -> _WorkerKind:
                    return _WorkerKind.BASIC
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="allows private type alias outside types module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/worker.py": dedent(
                    """
                type _WorkerResult = str | int


                def run_worker() -> _WorkerResult:
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="reports public type alias outside types module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/worker.py": dedent(
                    """
                type WorkerResult = str | int


                def run_worker() -> WorkerResult:
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC015",),
        ),
        CheckPathsTestCase(
            description="reports uppercase constant outside constants module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/view.py": dedent(
                    """
                DEFAULT_NAME = "demo"
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC027", "SC016"),
        ),
        CheckPathsTestCase(
            description="reports nested direct module outside helpers package",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/service.py": dedent(
                    """
                def build_service() -> str:
                    return "demo"
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC027",),
        ),
        CheckPathsTestCase(
            description="allows nested support module under helpers package",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/__init__.py": '"""Helpers."""\n',
                "src/sqlbuild/example/widget/helpers/service.py": dedent(
                    """
                def build_service() -> str:
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="allows focused modules under main package",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/__init__.py": '"""Main entry modules."""\n',
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                def load_example() -> str:
                    return _default_name()


                def _default_name() -> str:
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="allows flat public entry modules under main",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/__init__.py": '"""Main entry modules."""\n',
                "src/sqlbuild/example/widget/main/plan.py": dedent(
                    """
                from sqlbuild.example.widget.types import ExampleName


                def run_plan() -> ExampleName:
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="reports generic main.py inside main entry package",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/__init__.py": '"""Main entry modules."""\n',
                "src/sqlbuild/example/widget/main/main.py": dedent(
                    """
                def run_widget() -> str:
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC027",),
        ),
        CheckPathsTestCase(
            description="allows imports from parent shared package",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/shared/__init__.py": '"""Widget shared support."""\n',
                "src/sqlbuild/example/widget/shared/types.py": dedent(
                    """
                from typing import TypeAlias


                ExampleName: TypeAlias = str
                """
                ).strip()
                + "\n",
                "src/sqlbuild/example/widget/main/plan.py": dedent(
                    """
                from sqlbuild.example.widget.shared.types import ExampleName


                def run_plan() -> ExampleName:
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="reports concern subpackage under main when flat entries exist",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/__init__.py": '"""Main entry modules."""\n',
                "src/sqlbuild/example/widget/main/plan/__init__.py": '"""Plan command."""\n',
            },
            expected_violation_codes=("SC059",),
        ),
        CheckPathsTestCase(
            description="reports extra support module directly under main",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/__init__.py": '"""Main entry modules."""\n',
                "src/sqlbuild/example/widget/main/plan.py": dedent(
                    """
                def run_plan() -> str:
                    return "demo"
                """
                ).strip()
                + "\n",
                "src/sqlbuild/example/widget/main/preview.py": dedent(
                    """
                def render_preview() -> str:
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="reports multiple public functions in main package module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/__init__.py": '"""Main entry modules."""\n',
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                def load_example() -> str:
                    return "demo"


                def build_example() -> str:
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC019",),
        ),
        CheckPathsTestCase(
            description="allows entry module import from same package helpers",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/__init__.py": '"""Main entry modules."""\n',
                "src/sqlbuild/example/widget/main/plan.py": dedent(
                    """
                from sqlbuild.example.widget.helpers.backfill.run import run_backfill


                def run_plan() -> str:
                    return run_backfill()
                """
                ).strip()
                + "\n",
                "src/sqlbuild/example/widget/helpers/backfill/__init__.py": '"""Backfill helpers."""\n',
                "src/sqlbuild/example/widget/helpers/backfill/run.py": dedent(
                    """
                def run_backfill() -> str:
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="allows role package import from same package helpers",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/classes/__init__.py": '"""Widget classes."""\n',
                "src/sqlbuild/example/widget/classes/runner.py": dedent(
                    """
                from sqlbuild.example.widget.helpers.backfill.run import run_backfill


                class WidgetRunner:
                    def run(self) -> str:
                        return run_backfill()
                """
                ).strip()
                + "\n",
                "src/sqlbuild/example/widget/helpers/backfill/__init__.py": '"""Backfill helpers."""\n',
                "src/sqlbuild/example/widget/helpers/backfill/run.py": dedent(
                    """
                def run_backfill() -> str:
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="allows one main entry to import another main entry",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/__init__.py": '"""Main entry modules."""\n',
                "src/sqlbuild/example/widget/main/entry.py": dedent(
                    """
                from sqlbuild.example.widget.main.plan import run_plan


                def run_entry() -> str:
                    return run_plan()
                """
                ).strip()
                + "\n",
                "src/sqlbuild/example/widget/main/plan.py": dedent(
                    """
                def run_plan() -> str:
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="allows main entry import from same package classes",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/__init__.py": '"""Main entry modules."""\n',
                "src/sqlbuild/example/widget/main/run.py": dedent(
                    """
                from sqlbuild.example.widget.classes.runner import WidgetRunner


                def run_widget() -> str:
                    return WidgetRunner().run()
                """
                ).strip()
                + "\n",
                "src/sqlbuild/example/widget/classes/__init__.py": '"""Widget classes."""\n',
                "src/sqlbuild/example/widget/classes/runner.py": dedent(
                    """
                class WidgetRunner:
                    def run(self) -> str:
                        return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="allows helpers import from same package classes",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/__init__.py": '"""Helpers."""\n',
                "src/sqlbuild/example/widget/helpers/build.py": dedent(
                    """
                from sqlbuild.example.widget.classes.runner import WidgetRunner


                def build_widget() -> str:
                    return WidgetRunner().run()
                """
                ).strip()
                + "\n",
                "src/sqlbuild/example/widget/classes/__init__.py": '"""Widget classes."""\n',
                "src/sqlbuild/example/widget/classes/runner.py": dedent(
                    """
                class WidgetRunner:
                    def run(self) -> str:
                        return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="reports mixed flat module and concern subpackage under main",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/__init__.py": '"""Main entry modules."""\n',
                "src/sqlbuild/example/widget/main/plan.py": dedent(
                    """
                def run_plan() -> str:
                    return "demo"
                """
                ).strip()
                + "\n",
                "src/sqlbuild/example/widget/main/plan/__init__.py": '"""Plan command."""\n',
            },
            expected_violation_codes=("SC059",),
        ),
        CheckPathsTestCase(
            description="reports custom exception declared outside exceptions module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/service.py": dedent(
                    """
                class ExampleError(Exception):
                    pass


                def load_example() -> str:
                    return "demo"
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC027", "SC021"),
        ),
        CheckPathsTestCase(
            description="reports exceptions module nested under helpers package",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/exceptions.py": dedent(
                    """
                class ExampleError(Exception):
                    pass
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC021",),
        ),
        CheckPathsTestCase(
            description="reports multiple public functions in main entry module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                def load_example() -> str:
                    return "demo"


                def build_example() -> str:
                    return "demo"
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC019",),
        ),
        CheckPathsTestCase(
            description="reports assignments in main entry module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                VALUE = "demo"


                def load_example() -> str:
                    return VALUE
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC016", "SC020"),
        ),
        CheckPathsTestCase(
            description="reports too many private functions in main entry module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                def load_example() -> str:
                    return _first()


                def _first() -> str:
                    return "one"


                def _second() -> str:
                    return "two"


                def _third() -> str:
                    return "three"


                def _fourth() -> str:
                    return "four"


                def _fifth() -> str:
                    return "five"
                """
                ).strip()
                + "\n"
            },
            expected_violation_codes=("SC026",),
        ),
        CheckPathsTestCase(
            description="reports main module inside helpers package",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/__init__.py": '"""Helpers."""\n',
                "src/sqlbuild/example/widget/helpers/main.py": dedent(
                    """
                def main() -> int:
                    return 0
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC010",),
        ),
        CheckPathsTestCase(
            description="allows direct role modules inside helper subpackages",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/__init__.py": '"""Helpers."""\n',
                "src/sqlbuild/example/widget/helpers/diff/__init__.py": '"""Diff helpers."""\n',
                "src/sqlbuild/example/widget/helpers/diff/parse.py": dedent(
                    """
                def parse_diff() -> str:
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="allows conventional files inside helper subpackages",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/__init__.py": '"""Helpers."""\n',
                "src/sqlbuild/example/widget/helpers/diff/__init__.py": '"""Diff helpers."""\n',
                "src/sqlbuild/example/widget/helpers/diff/constants.py": 'DEFAULT_KIND = "demo"\n',
                "src/sqlbuild/example/widget/helpers/diff/models.py": dedent(
                    """
                from dataclasses import dataclass


                @dataclass(frozen=True)
                class DiffModel:
                    name: str
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="reports main module inside helper subpackages",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/__init__.py": '"""Helpers."""\n',
                "src/sqlbuild/example/widget/helpers/diff/__init__.py": '"""Diff helpers."""\n',
                "src/sqlbuild/example/widget/helpers/diff/main.py": dedent(
                    """
                def parse_diff() -> str:
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC022",),
        ),
        CheckPathsTestCase(
            description="reports nested package inside helper subpackages",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/__init__.py": '"""Helpers."""\n',
                "src/sqlbuild/example/widget/helpers/diff/__init__.py": '"""Diff helpers."""\n',
                "src/sqlbuild/example/widget/helpers/diff/parsing/__init__.py": '"""Parsing."""\n',
            },
            expected_violation_codes=("SC022", "SC030"),
        ),
        CheckPathsTestCase(
            description="allows sibling public main import",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/discovery/__init__.py": '"""Discovery."""\n',
                "src/sqlbuild/example/discovery/main/__init__.py": '"""Discovery entries."""\n',
                "src/sqlbuild/example/discovery/main/discover.py": dedent(
                    """
                from sqlbuild.example.refs.main.parse import parse_ref


                def discover_name() -> str:
                    return parse_ref()
                """
                ).strip()
                + "\n",
                "src/sqlbuild/example/refs/__init__.py": '"""Refs."""\n',
                "src/sqlbuild/example/refs/main/__init__.py": '"""Ref entries."""\n',
                "src/sqlbuild/example/refs/main/parse.py": dedent(
                    """
                def parse_ref() -> str:
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="allows sibling main package public entry import",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/discovery/__init__.py": '"""Discovery."""\n',
                "src/sqlbuild/example/discovery/main/__init__.py": '"""Discovery entries."""\n',
                "src/sqlbuild/example/discovery/main/discover.py": dedent(
                    """
                from sqlbuild.example.refs.main.parse import parse_ref


                def discover_name() -> str:
                    return parse_ref()
                """
                ).strip()
                + "\n",
                "src/sqlbuild/example/refs/__init__.py": '"""Refs."""\n',
                "src/sqlbuild/example/refs/main/__init__.py": '"""Ref entries."""\n',
                "src/sqlbuild/example/refs/main/parse.py": dedent(
                    """
                def parse_ref() -> str:
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="reports sibling subpackage internal import",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/discovery/__init__.py": '"""Discovery."""\n',
                "src/sqlbuild/example/discovery/main/__init__.py": '"""Discovery entries."""\n',
                "src/sqlbuild/example/discovery/main/discover.py": dedent(
                    """
                from sqlbuild.example.refs.helpers.parse import parse_ref


                def discover_name() -> str:
                    return parse_ref()
                """
                ).strip()
                + "\n",
                "src/sqlbuild/example/refs/__init__.py": '"""Refs."""\n',
                "src/sqlbuild/example/refs/helpers/__init__.py": '"""Ref helpers."""\n',
                "src/sqlbuild/example/refs/helpers/parse.py": dedent(
                    """
                def parse_ref() -> str:
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC033",),
        ),
        CheckPathsTestCase(
            description="allows sibling helper subpackage import",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/changes/__init__.py": '"""Changes."""\n',
                "src/sqlbuild/example/widget/helpers/changes/detect.py": dedent(
                    """
                from sqlbuild.example.widget.helpers.identity.hashing import hash_value


                def detect() -> str:
                    return hash_value("demo")
                """
                ).strip()
                + "\n",
                "src/sqlbuild/example/widget/helpers/identity/__init__.py": '"""Identity."""\n',
                "src/sqlbuild/example/widget/helpers/identity/hashing.py": dedent(
                    """
                def hash_value(value: str) -> str:
                    return value
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="allows sibling models import",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/discovery/__init__.py": '"""Discovery."""\n',
                "src/sqlbuild/example/discovery/main/__init__.py": '"""Discovery entries."""\n',
                "src/sqlbuild/example/discovery/main/discover.py": dedent(
                    """
                from sqlbuild.example.refs.models import RefModel


                def discover_name() -> RefModel:
                    return RefModel(name="demo")
                """
                ).strip()
                + "\n",
                "src/sqlbuild/example/refs/__init__.py": '"""Refs."""\n',
                "src/sqlbuild/example/refs/models.py": dedent(
                    """
                from dataclasses import dataclass


                @dataclass(frozen=True)
                class RefModel:
                    name: str
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="reports main module inside shared package",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/shared/__init__.py": '"""Shared."""\n',
                "src/sqlbuild/example/shared/main.py": dedent(
                    """
                def main() -> int:
                    return 0
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC012",),
        ),
        CheckPathsTestCase(
            description="reports shared package importing sibling internals",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/shared/__init__.py": '"""Shared."""\n',
                "src/sqlbuild/example/shared/types.py": dedent(
                    """
                from sqlbuild.example.refs.helpers.parse import parse_ref


                ExampleName = str
                value = parse_ref()
                """
                ).strip()
                + "\n",
                "src/sqlbuild/example/refs/__init__.py": '"""Refs."""\n',
                "src/sqlbuild/example/refs/helpers/__init__.py": '"""Ref helpers."""\n',
                "src/sqlbuild/example/refs/helpers/parse.py": dedent(
                    """
                def parse_ref() -> str:
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC013", "SC033"),
        ),
        CheckPathsTestCase(
            description="allows parent shared import from subpackage",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/discovery/__init__.py": '"""Discovery."""\n',
                "src/sqlbuild/example/discovery/main/__init__.py": '"""Discovery entries."""\n',
                "src/sqlbuild/example/discovery/main/discover.py": dedent(
                    """
                from sqlbuild.example.shared.types import ExampleName


                def discover_name() -> ExampleName:
                    return "demo"
                """
                ).strip()
                + "\n",
                "src/sqlbuild/example/shared/__init__.py": '"""Shared."""\n',
                "src/sqlbuild/example/shared/types.py": "ExampleName = str\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="allows imports from top-level shared boundary",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/shared/__init__.py": '"""Shared."""\n',
                "src/sqlbuild/shared/helpers/__init__.py": '"""Shared helpers."""\n',
                "src/sqlbuild/shared/helpers/cli_style.py": dedent(
                    """
                class CliStyle:
                    def __init__(self, *, use_color: bool) -> None:
                        self.use_color = use_color

                    def accent(self, text: str) -> str:
                        return text
                """
                ).strip()
                + "\n",
                "src/sqlbuild/example/discovery/__init__.py": '"""Discovery."""\n',
                "src/sqlbuild/example/discovery/main/__init__.py": '"""Discovery entries."""\n',
                "src/sqlbuild/example/discovery/main/discover.py": dedent(
                    """
                from sqlbuild.shared.helpers.output.cli_style import CliStyle


                def discover_name() -> str:
                    return CliStyle(use_color=False).accent("demo")
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="allows adapters client module with a single public class",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/integrations/__init__.py": '"""Integrations."""\n',
                "src/sqlbuild/adapters/clickhouse/__init__.py": '"""ClickHouse integration."""\n',
                "src/sqlbuild/adapters/clickhouse/models.py": dedent(
                    """
                from dataclasses import dataclass


                @dataclass(frozen=True)
                class ClickHouseConnectionConfig:
                    host: str
                """
                ).strip()
                + "\n",
                "src/sqlbuild/adapters/clickhouse/client.py": dedent(
                    """
                from sqlbuild.adapters.clickhouse.models import ClickHouseConnectionConfig


                class ClickHouseClient:
                    @classmethod
                    def from_config(cls, config: ClickHouseConnectionConfig) -> "ClickHouseClient":
                        return cls()
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="reports main module inside adapters package",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/integrations/__init__.py": '"""Integrations."""\n',
                "src/sqlbuild/adapters/clickhouse/__init__.py": '"""ClickHouse integration."""\n',
                "src/sqlbuild/adapters/clickhouse/main.py": dedent(
                    """
                def create_client() -> object:
                    return object()
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC023",),
        ),
        CheckPathsTestCase(
            description="reports multiple public classes in adapters client module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/integrations/__init__.py": '"""Integrations."""\n',
                "src/sqlbuild/adapters/clickhouse/__init__.py": '"""ClickHouse integration."""\n',
                "src/sqlbuild/adapters/clickhouse/client.py": dedent(
                    """
                class ClickHouseClient:
                    pass


                class BackupClient:
                    pass
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC024",),
        ),
        CheckPathsTestCase(
            description="reports top level function in adapters client module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/integrations/__init__.py": '"""Integrations."""\n',
                "src/sqlbuild/adapters/clickhouse/__init__.py": '"""ClickHouse integration."""\n',
                "src/sqlbuild/adapters/clickhouse/client.py": dedent(
                    """
                class ClickHouseClient:
                    pass


                def create_client() -> ClickHouseClient:
                    return ClickHouseClient()
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC025",),
        ),
        CheckPathsTestCase(
            description="reports adapter-local adapters helpers module",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/integrations/__init__.py": '"""Integrations."""\n',
                "src/sqlbuild/adapters/clickhouse/__init__.py": '"""ClickHouse integration."""\n',
                "src/sqlbuild/adapters/clickhouse/helpers.py": dedent(
                    """
                def render_clickhouse_sql() -> str:
                    return "SELECT 1"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC003", "SC004", "SC040"),
        ),
        CheckPathsTestCase(
            description="reports private dataclass after function definition",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/build.py": dedent(
                    """
                from __future__ import annotations

                from dataclasses import dataclass


                def do_work() -> str:
                    return "done"


                @dataclass(frozen=True)
                class _InternalState:
                    value: str
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC034",),
        ),
        CheckPathsTestCase(
            description="reports private constant after function definition",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/helpers/build.py": dedent(
                    """
                from __future__ import annotations


                def do_work() -> str:
                    return "done"


                _INTERNAL_VALUE: int = 42
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC034",),
        ),
        CheckPathsTestCase(
            description="reports raw built-in raise in production code",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                def load_example() -> str:
                    raise ValueError("bad example")
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC035",),
        ),
        CheckPathsTestCase(
            description="reports assert in production code",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                def load_example(value: str | None) -> str:
                    assert value is not None
                    return value
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC036",),
        ),
        CheckPathsTestCase(
            description="reports first class adapter BaseAdapter method alias",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/adapters/example/client.py": dedent(
                    """
                from sqlbuild.adapter.base.base_adapter import BaseAdapter


                class ExampleAdapter(BaseAdapter):
                    render_identifier = BaseAdapter.render_identifier
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC037",),
        ),
        CheckPathsTestCase(
            description="reports first class adapter super delegation in contract method",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/adapters/example/client.py": dedent(
                    """
                from sqlbuild.adapter.base.base_adapter import BaseAdapter


                class ExampleAdapter(BaseAdapter):
                    def render_identifier(self, name: str) -> str:
                        return super().render_identifier(name)
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC038",),
        ),
        CheckPathsTestCase(
            description="allows raw built-in names outside raise and assert contexts",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                def load_example(error: ValueError) -> str:
                    return str(error)
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="reports silent broad exception probe answers in runtime code",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                def load_examples(values: list[str]) -> tuple[object, ...]:
                    try:
                        missing_name: str | None = "present"
                    except Exception:
                        return None

                    try:
                        probe_flag: bool = True
                    except Exception:
                        return False

                    try:
                        probe_map: dict[str, str] = {"present": "yes"}
                    except Exception:
                        return {}

                    try:
                        probe_tuple: tuple[str, ...] = ("present",)
                    except Exception:
                        return ()

                    found: list[str] = []
                    for value in values:
                        try:
                            found.append(value)
                        except Exception:
                            continue
                    return (missing_name, probe_flag, probe_map, probe_tuple, found)
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC044", "SC044", "SC044", "SC044", "SC044"),
        ),
        CheckPathsTestCase(
            description="allows broad exception fallbacks that log or bind the exception",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                def load_examples() -> tuple[bool, bool]:
                    try:
                        logged_probe: bool = True
                    except Exception:
                        log_debug_event("probe failed")
                        logged_probe = False

                    try:
                        failed_result: bool = True
                    except Exception as exc:
                        failed_result = build_failed_result(exc)
                    return (logged_probe, failed_result)
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="allows silent broad exception probe answers outside runtime code",
            repo_files=compliant_repo_files()
            | {
                "scripts/check_probe.py": dedent(
                    """
                def probe() -> bool:
                    try:
                        return True
                    except Exception:
                        return False
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="flags warehouse metadata calls inside a loop as N+1 risks",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                def load(adapter, connection, entries) -> list[str]:
                    found: list[str] = []
                    for entry in entries:
                        if adapter.relation_exists(
                            connection, database=None, schema="s", name=entry
                        ):
                            found.append(entry)
                    return found
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC051",),
        ),
        CheckPathsTestCase(
            description="flags describe relation calls inside a loop as N+1 risks",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/describe.py": dedent(
                    """
                def describe(adapter, connection, relations) -> list[object]:
                    columns: list[object] = []
                    for relation in relations:
                        columns.extend(adapter.describe_relation(connection, relation))
                    return columns
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC051",),
        ),
        CheckPathsTestCase(
            description="flags query column names calls inside a loop as N+1 risks",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/columns.py": dedent(
                    """
                def columns(adapter, connection, expressions) -> dict[str, tuple[str, ...]]:
                    result: dict[str, tuple[str, ...]] = {}
                    for name, sql in expressions.items():
                        result[name] = adapter.query_column_names(connection, sql)
                    return result
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC051",),
        ),
        CheckPathsTestCase(
            description="flags schema exists calls inside a loop as N+1 risks",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/schemas.py": dedent(
                    """
                def schemas(adapter, connection, names) -> list[str]:
                    existing: list[str] = []
                    for name in names:
                        if adapter.schema_exists(connection, schema=name):
                            existing.append(name)
                    return existing
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC051",),
        ),
        CheckPathsTestCase(
            description="flags table freshness metadata calls inside a loop as N+1 risks",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/freshness.py": dedent(
                    """
                def freshness(adapter, connection, names) -> list[object]:
                    records: list[object] = []
                    for name in names:
                        records.append(
                            adapter.get_table_freshness_metadata(
                                connection, database=None, schema="s", name=name
                            )
                        )
                    return records
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC051",),
        ),
        CheckPathsTestCase(
            description="allows warehouse metadata calls gathered once before a loop",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/gather.py": dedent(
                    """
                def gather(adapter, connection, entries) -> list[str]:
                    relations = adapter.list_relations(
                        connection, database=None, schemas=("s",)
                    )
                    names = {relation.name for relation in relations}
                    return [entry for entry in entries if entry in names]
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="flags a transitively metadata-bearing helper called inside a loop",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/indirect.py": dedent(
                    """
                def _exists(adapter, connection, name) -> bool:
                    return adapter.relation_exists(
                        connection, database=None, schema="s", name=name
                    )


                def _exists_named(adapter, connection, name) -> bool:
                    return _exists(adapter, connection, name)


                def collect_missing(adapter, connection, entries) -> list[str]:
                    missing: list[str] = []
                    for entry in entries:
                        if not _exists_named(adapter, connection, entry):
                            missing.append(entry)
                    return missing
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC051",),
        ),
        CheckPathsTestCase(
            description="does not flag a same-named helper that is not metadata-bearing",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/unrelated.py": dedent(
                    """
                def _exists(value) -> bool:
                    return value is not None


                def collect(values) -> list[object]:
                    return [value for value in values if _exists(value)]
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="flags ad hoc dbt ref-kind scans outside centralized resolver",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/integrations/dbt/helpers/planning/ref_scan.py": dedent(
                    """
                from sqlbuild.shared.types import SqlReferenceKind


                def is_dbt_ref(reference) -> bool:
                    return reference.ref_kind == SqlReferenceKind.DBT_REF
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC052",),
        ),
        CheckPathsTestCase(
            description="allows dbt ref-kind scan in centralized resolver",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/integrations/dbt/helpers/manifest/sqlbuild_refs.py": dedent(
                    """
                from sqlbuild.shared.types import SqlReferenceKind


                def is_dbt_ref(reference) -> bool:
                    return reference.ref_kind == SqlReferenceKind.DBT_REF
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="flags ad hoc dbt neutral graph key construction",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/integrations/dbt/helpers/planning/projection.py": dedent(
                    """
                from sqlbuild.compiler.planner.models import GraphNodeKey


                def project(unique_id: str) -> GraphNodeKey:
                    return GraphNodeKey(node_type="dbt", node_name=unique_id)
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC053",),
        ),
        CheckPathsTestCase(
            description="flags ad hoc selector plus parsing in dbt code",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/integrations/dbt/helpers/selection/core.py": dedent(
                    """
                def parse(raw: str) -> tuple[bool, str]:
                    return raw.startswith("+"), raw.lstrip("+")
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC054", "SC054"),
        ),
        CheckPathsTestCase(
            description="flags load_project_macros usage outside the compile-input load site",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                from sqlbuild.compiler.compile.helpers.render.macros import load_project_macros


                def load_example(macro_files: tuple) -> dict:
                    return load_project_macros(macro_files)
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC033", "SC062", "SC062"),
        ),
        CheckPathsTestCase(
            description="allows load_project_macros in build_compile_inputs",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/compiler/__init__.py": '"""Compiler domain."""\n',
                "src/sqlbuild/compiler/compile/__init__.py": '"""Compile package."""\n',
                "src/sqlbuild/compiler/compile/main/__init__.py": '"""Compile entries."""\n',
                "src/sqlbuild/compiler/compile/main/build_compile_inputs.py": dedent(
                    """
                from sqlbuild.compiler.compile.helpers.render.macros import load_project_macros


                def build_compile_inputs(macro_files: tuple) -> dict:
                    return load_project_macros(macro_files)
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
        CheckPathsTestCase(
            description="flags multiline docstrings",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    '''
                def load_example() -> str:
                    """Load an example.

                    More context belongs in docs or tests.
                    """

                    return "demo"
                '''
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC055",),
        ),
        CheckPathsTestCase(
            description="flags standalone comments",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                def load_example() -> str:
                    # Claude thought this comment was helpful.
                    return "demo"
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("SC056",),
        ),
        CheckPathsTestCase(
            description="allows tool pragma comments",
            repo_files=compliant_repo_files()
            | {
                "src/sqlbuild/example/widget/main/load.py": dedent(
                    """
                def load_example(value) -> str:
                    return value  # type: ignore[no-any-return]
                """
                ).strip()
                + "\n",
            },
            expected_violation_codes=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_repo_slice_when_checking_paths_then_returns_expected_violation_codes(
    test_case: CheckPathsTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    violation_codes: tuple[str, ...] = collect_violation_codes(tmp_path)

    assert violation_codes == test_case.expected_violation_codes


@pytest.mark.parametrize(
    "test_case",
    [
        CheckCliMainTestCase(
            description="returns zero for a compliant repo slice",
            repo_files=compliant_repo_files(),
            cli_paths=("src", "scripts"),
            expected_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_repo_slice_when_running_cli_main_then_returns_expected_exit_code(
    test_case: CheckCliMainTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    exit_code: int = main([str(tmp_path / path) for path in test_case.cli_paths])

    assert exit_code == test_case.expected_exit_code


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
