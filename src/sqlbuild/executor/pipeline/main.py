"""Executor pipeline orchestration for build execution."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.main import execute_build_plan
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.pipeline.helpers.auditing import (
    run_audit_pipeline as run_audit_pipeline,
)
from sqlbuild.executor.pipeline.helpers.seeding import (
    run_seed_pipeline as run_seed_pipeline,
)
from sqlbuild.executor.pipeline.helpers.settings import resolve_promotion_mode
from sqlbuild.executor.pipeline.helpers.testing import (
    run_test_pipeline as run_test_pipeline,
)
from sqlbuild.executor.shared.types import TablePromotionMode
from sqlbuild.spec.models.project import SettingsConfig


def run_build_pipeline(
    *,
    plan: PlanOutput,
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    settings: SettingsConfig,
    run_id: str,
    fingerprint_schema: str | None = None,
    run_tests: bool = True,
    run_audits: bool = True,
    fail_fast: bool = False,
    on_node_start: Callable[[str, str], None] | None = None,
    on_node_complete: Callable[[object], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> BuildExecutionResult:
    """Execute a full build pipeline: resolve settings, open connection, run plan, close."""

    promotion_mode: TablePromotionMode = resolve_promotion_mode(settings=settings, adapter=adapter)
    connection: Any = adapter.connect(connection_config)
    try:
        return execute_build_plan(
            plan=plan,
            adapter=adapter,
            connection=connection,
            promotion_mode=promotion_mode,
            run_id=run_id,
            fingerprint_schema=fingerprint_schema,
            run_audits=run_audits,
            run_tests=run_tests,
            fail_fast=fail_fast,
            on_node_start=on_node_start,
            on_node_complete=on_node_complete,
            on_progress=on_progress,
        )
    finally:
        adapter.close(connection)
