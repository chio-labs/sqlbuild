"""Executor pipeline orchestration for build execution."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.types import TablePromotionMode
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.main.execute import execute_build_plan
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.custom.models import MaterializationResult
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
from sqlbuild.spec.models.project import SettingsConfig


def run_build_pipeline(
    *,
    plan: PlanOutput,
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    settings: SettingsConfig,
    run_id: str,
    run_tests: bool = True,
    run_audits: bool = True,
    fail_fast: bool = False,
    max_concurrency: int = 1,
    on_node_start: Callable[[str, str], None] | None = None,
    on_node_complete: Callable[[object], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_sub_progress: Callable[[str], None] | None = None,
    custom_materializations: dict[str, Callable[..., MaterializationResult]] | None = None,
    environment: str = "",
    effective_vars: dict[str, str] | None = None,
) -> BuildExecutionResult:
    """Execute a full build pipeline: resolve settings, open connections, run plan, close."""

    promotion_mode: TablePromotionMode = resolve_promotion_mode(settings=settings, adapter=adapter)
    effective_concurrency: int = max(1, max_concurrency)
    logger: logging.Logger = logging.getLogger("sqlbuild.executor.pipeline")
    logger.debug("open scheduler connection")
    scheduler_connection: Any = adapter.connect(connection_config)
    worker_connections: list[Any] = []
    _i: int
    for _i in range(effective_concurrency):
        logger.debug("open worker connection index=%s", _i)
        worker_connections.append(adapter.connect(connection_config))
    try:
        return execute_build_plan(
            plan=plan,
            adapter=adapter,
            connections=tuple(worker_connections),
            scheduler_connection=scheduler_connection,
            promotion_mode=promotion_mode,
            run_id=run_id,
            query_change_tracking=settings.query_change_tracking,
            run_audits=run_audits,
            run_tests=run_tests,
            fail_fast=fail_fast,
            on_node_start=on_node_start,
            on_node_complete=on_node_complete,
            on_progress=on_progress,
            custom_materializations=custom_materializations,
            environment=environment,
            effective_vars=effective_vars,
            on_sub_progress=on_sub_progress,
        )
    finally:
        conn: Any
        for _i, conn in enumerate(worker_connections):
            logger.debug("close worker connection index=%s", _i)
            adapter.close(conn)
        logger.debug("close scheduler connection")
        adapter.close(scheduler_connection)
