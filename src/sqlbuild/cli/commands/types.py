"""CLI command type-layer declarations."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlbuild.cli.commands.models import LineageCommandRequest, ScopeCommandRequest
    from sqlbuild.compiler.scopes.models import ScopeIndex


class CompileLineageMode(StrEnum):
    """Column lineage mode for compile output."""

    FAST = "fast"
    RICH = "rich"
    NONE = "none"


class DebugCheckStatus(StrEnum):
    OK = "OK"
    ERROR = "ERROR"
    SKIP = "SKIP"


class CliCommand(StrEnum):
    COMPILE = "compile"
    DAG = "dag"
    PLAN = "plan"
    FRESHNESS = "freshness"
    BUILD = "build"
    TEST = "test"
    CHECK = "check"
    AUDIT = "audit"
    LOAD = "load"
    SEED = "seed"
    CLONE = "clone"
    DIFF = "diff"
    DEBUG = "debug"
    LINEAGE = "lineage"
    QUERY = "query"
    COST = "cost"
    CLEAN = "clean"
    JANITOR = "janitor"
    INIT = "init"
    PLAYGROUND = "playground"
    SCENARIO = "scenario"
    DBT = "dbt"
    SKILLS = "skills"
    FORMAT = "format"
    RULES = "rules"
    SCOPE = "scope"
    CONTRACT = "contract"


class ScopeCommandHandler(Protocol):
    def __call__(self, *, request: ScopeCommandRequest) -> int: ...


class ScopeIndexLoader(Protocol):
    def __call__(self, *, project_dir: Path, no_cache: bool = False) -> ScopeIndex: ...


class DagCommandHandler(Protocol):
    def __call__(
        self,
        project_dir: Path | None,
        *,
        no_sql_validation: bool,
        json_output: bool,
        cli_vars: dict[str, object] | None,
    ) -> int: ...


class QueryCommandHandler(Protocol):
    def __call__(
        self,
        project_dir: Path | None,
        *,
        sql: str | None,
        query_file: Path | None,
        selected_target: str | None,
        output_format: str,
        limit: int | None,
    ) -> int: ...


class DebugCommandHandler(Protocol):
    def __call__(
        self,
        project_dir: Path | None,
        *,
        no_color: bool,
        no_connection: bool,
        selected_target: str | None,
        json_output: bool,
    ) -> int: ...


class LineageCommandHandler(Protocol):
    def __call__(self, request: LineageCommandRequest) -> int: ...


class SkillsUpdateCommandHandler(Protocol):
    def __call__(
        self,
        project_dir: Path | None,
        *,
        global_install: bool,
        targets: tuple[str, ...],
        force: bool,
    ) -> int: ...


class FormatCommandHandler(Protocol):
    def __call__(
        self,
        project_dir: Path | None,
        *,
        select: tuple[str, ...],
        exclude: tuple[str, ...],
        check: bool,
        diff: bool,
        fixtures_only: bool,
        json_output: bool,
        no_color: bool,
    ) -> int: ...


class FreshnessSourceStatus(StrEnum):
    """Command status for one source freshness observation."""

    OBSERVED = "observed"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    TOLERATED = "tolerated"
    UNKNOWN = "unknown"
    ERROR = "error"


class PlaygroundTemplate(StrEnum):
    """Available `sqb playground` templates."""

    WAFFLE_SHOP = "waffle_shop"
    LOADER_WAFFLE_SHOP = "loader_waffle_shop"
    DAGSTER = "dagster"
    RIVERS = "rivers"
    PYTHON_NODES = "python_nodes"
