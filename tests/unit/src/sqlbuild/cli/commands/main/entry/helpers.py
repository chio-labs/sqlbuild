"""Test helpers for CLI entry tests."""

from __future__ import annotations

from typing import Any

from sqlbuild.cli.commands.main.helpers.entry.models import CliEntrypointHandlers


def noop_handler(*_a: Any, **_k: Any) -> int:
    return 0


def build_handlers(**overrides: Any) -> CliEntrypointHandlers:
    """Build handlers with noop defaults, overriding specific slots."""

    return CliEntrypointHandlers(
        run_compile=overrides.get("run_compile", noop_handler),
        run_plan=overrides.get("run_plan", noop_handler),
        run_build=overrides.get("run_build", noop_handler),
        run_run=overrides.get("run_run", noop_handler),
        run_test=overrides.get("run_test", noop_handler),
        run_audit=overrides.get("run_audit", noop_handler),
        run_seed=overrides.get("run_seed", noop_handler),
        run_clone=overrides.get("run_clone", noop_handler),
        run_diff=overrides.get("run_diff", noop_handler),
        run_query=overrides.get("run_query", noop_handler),
        run_lineage=overrides.get("run_lineage", noop_handler),
        run_janitor=overrides.get("run_janitor", noop_handler),
    )
