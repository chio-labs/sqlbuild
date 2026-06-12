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
        run_dag=overrides.get("run_dag", noop_handler),
        run_plan=overrides.get("run_plan", noop_handler),
        run_dbt_plan=overrides.get("run_dbt_plan", noop_handler),
        run_dbt_run=overrides.get("run_dbt_run", noop_handler),
        run_dbt_build=overrides.get("run_dbt_build", noop_handler),
        run_dbt_test=overrides.get("run_dbt_test", noop_handler),
        run_dbt_debug=overrides.get("run_dbt_debug", noop_handler),
        run_build=overrides.get("run_build", noop_handler),
        run_freshness=overrides.get("run_freshness", noop_handler),
        run_test=overrides.get("run_test", noop_handler),
        run_check=overrides.get("run_check", noop_handler),
        run_audit=overrides.get("run_audit", noop_handler),
        run_seed=overrides.get("run_seed", noop_handler),
        run_load=overrides.get("run_load", noop_handler),
        run_clone=overrides.get("run_clone", noop_handler),
        run_diff=overrides.get("run_diff", noop_handler),
        run_reconcile=overrides.get("run_reconcile", noop_handler),
        run_promote=overrides.get("run_promote", noop_handler),
        run_rollback=overrides.get("run_rollback", noop_handler),
        run_query=overrides.get("run_query", noop_handler),
        run_debug=overrides.get("run_debug", noop_handler),
        run_lineage=overrides.get("run_lineage", noop_handler),
        run_janitor=overrides.get("run_janitor", noop_handler),
        run_state=overrides.get("run_state", noop_handler),
        run_init=overrides.get("run_init", noop_handler),
        run_playground=overrides.get("run_playground", noop_handler),
        run_skills_update=overrides.get("run_skills_update", noop_handler),
        run_scenario=overrides.get("run_scenario", noop_handler),
        run_scenario_capture=overrides.get("run_scenario_capture", noop_handler),
    )
