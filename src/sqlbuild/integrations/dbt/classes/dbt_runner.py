"""dbt CLI runner."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from sqlbuild.integrations.dbt.exceptions import DbtInteropRuntimeError
from sqlbuild.integrations.dbt.main.cli._build_compile_argv import build_dbt_compile_argv
from sqlbuild.integrations.dbt.main.cli._build_debug_argv import build_dbt_debug_argv
from sqlbuild.integrations.dbt.main.cli._build_deps_argv import build_dbt_deps_argv
from sqlbuild.integrations.dbt.main.cli._build_ls_argv import build_dbt_ls_argv
from sqlbuild.integrations.dbt.main.cli._parse_ls_json_lines import parse_dbt_ls_json_lines
from sqlbuild.integrations.dbt.main.cli._resolve_executable import resolve_dbt_executable
from sqlbuild.integrations.dbt.models import DbtCliOptions, DbtCommandResult, DbtLsResult
from sqlbuild.integrations.dbt.types import DbtInvoker


class DbtRunner:
    """Small dbt CLI runner with per-invocation dbt ls memoization."""

    def __init__(
        self, *, dbt_executable: str | None = None, invoker: DbtInvoker | None = None
    ) -> None:
        self.dbt_executable = dbt_executable or resolve_dbt_executable()
        self.invoker = invoker
        self._ls_cache: dict[tuple[str, ...], DbtLsResult] = {}

    def compile(self, *, options: DbtCliOptions, full_refresh: bool = False) -> DbtCommandResult:
        """Run dbt compile."""

        argv: tuple[str, ...] = build_dbt_compile_argv(
            dbt_executable=self.dbt_executable, options=options, full_refresh=full_refresh
        )
        return self._invoke(argv=argv, cwd=options.project_dir)

    def deps(self, *, options: DbtCliOptions) -> DbtCommandResult:
        """Run dbt deps."""

        argv: tuple[str, ...] = build_dbt_deps_argv(
            dbt_executable=self.dbt_executable,
            options=options,
        )
        return self._invoke(argv=argv, cwd=options.project_dir)

    def debug(self, *, options: DbtCliOptions, args: Sequence[str] = ()) -> DbtCommandResult:
        """Run dbt debug."""

        argv: tuple[str, ...] = build_dbt_debug_argv(
            dbt_executable=self.dbt_executable, options=options, args=args
        )
        return self._invoke(argv=argv, cwd=options.project_dir)

    def ls(
        self,
        *,
        options: DbtCliOptions,
        select: Sequence[str] = (),
        exclude: Sequence[str] = (),
        resource_types: Sequence[str] = (),
    ) -> DbtLsResult:
        """Run dbt ls and parse selected nodes."""

        argv: tuple[str, ...] = build_dbt_ls_argv(
            dbt_executable=self.dbt_executable,
            options=options,
            select=select,
            exclude=exclude,
            resource_types=resource_types,
        )
        cached: DbtLsResult | None = self._ls_cache.get(argv)
        if cached is not None:
            return cached
        command: DbtCommandResult = self._invoke(argv=argv, cwd=options.project_dir)
        result: DbtLsResult = DbtLsResult(
            nodes=parse_dbt_ls_json_lines(stdout=command.stdout), command=command
        )
        self._ls_cache[argv] = result
        return result

    def _invoke(self, *, argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
        if self.invoker is not None:
            return cast(DbtCommandResult, self.invoker(argv=argv, cwd=cwd))
        try:
            completed: subprocess.CompletedProcess[str] = subprocess.run(
                argv,
                cwd=cwd,
                capture_output=True,
                check=False,
                text=True,
            )
        except OSError as error:
            raise DbtInteropRuntimeError(
                "failed to execute dbt",
                help=str(error),
            ) from error
        return DbtCommandResult(
            argv=argv,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def invoke(self, *, argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
        """Run an explicit dbt argv."""

        return self._invoke(argv=argv, cwd=cwd)
