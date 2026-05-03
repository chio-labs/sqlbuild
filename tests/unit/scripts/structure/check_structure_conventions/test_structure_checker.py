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

TEST_CASES: list[CheckPathsTestCase] = [
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
        description="reports subpackage under main",
        repo_files=compliant_repo_files()
        | {
            "src/sqlbuild/example/widget/main/__init__.py": '"""Main entry modules."""\n',
            "src/sqlbuild/example/widget/main/plan/__init__.py": '"""Plan command."""\n',
        },
        expected_violation_codes=("SC030",),
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
        description="reports sibling entry internal helper import under main",
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
        description="reports subpackage under main even when flat entry exists",
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
        expected_violation_codes=("SC030",),
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
            "src/sqlbuild/shared/helpers/colors.py": dedent(
                """
                def blue(text: str) -> str:
                    return text
                """
            ).strip()
            + "\n",
            "src/sqlbuild/example/discovery/__init__.py": '"""Discovery."""\n',
            "src/sqlbuild/example/discovery/main/__init__.py": '"""Discovery entries."""\n',
            "src/sqlbuild/example/discovery/main/discover.py": dedent(
                """
                from sqlbuild.shared.helpers.colors import blue


                def discover_name() -> str:
                    return blue("demo")
                """
            ).strip()
            + "\n",
        },
        expected_violation_codes=(),
    ),
    CheckPathsTestCase(
        description="allows integrations client module with a single public class",
        repo_files=compliant_repo_files()
        | {
            "src/sqlbuild/integrations/__init__.py": '"""Integrations."""\n',
            "src/sqlbuild/integrations/clickhouse/__init__.py": '"""ClickHouse integration."""\n',
            "src/sqlbuild/integrations/clickhouse/models.py": dedent(
                """
                from dataclasses import dataclass


                @dataclass(frozen=True)
                class ClickHouseConnectionConfig:
                    host: str
                """
            ).strip()
            + "\n",
            "src/sqlbuild/integrations/clickhouse/client.py": dedent(
                """
                from sqlbuild.integrations.clickhouse.models import ClickHouseConnectionConfig


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
        description="reports main module inside integrations package",
        repo_files=compliant_repo_files()
        | {
            "src/sqlbuild/integrations/__init__.py": '"""Integrations."""\n',
            "src/sqlbuild/integrations/clickhouse/__init__.py": '"""ClickHouse integration."""\n',
            "src/sqlbuild/integrations/clickhouse/main.py": dedent(
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
        description="reports multiple public classes in integrations client module",
        repo_files=compliant_repo_files()
        | {
            "src/sqlbuild/integrations/__init__.py": '"""Integrations."""\n',
            "src/sqlbuild/integrations/clickhouse/__init__.py": '"""ClickHouse integration."""\n',
            "src/sqlbuild/integrations/clickhouse/client.py": dedent(
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
        description="reports top level function in integrations client module",
        repo_files=compliant_repo_files()
        | {
            "src/sqlbuild/integrations/__init__.py": '"""Integrations."""\n',
            "src/sqlbuild/integrations/clickhouse/__init__.py": '"""ClickHouse integration."""\n',
            "src/sqlbuild/integrations/clickhouse/client.py": dedent(
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
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
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
    ids=["returns zero for a compliant repo slice"],
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
