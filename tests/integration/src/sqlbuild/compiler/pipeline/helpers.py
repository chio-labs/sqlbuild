from __future__ import annotations

import itertools
import json
import random
import signal
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.cli.commands.main.entrypoint.entry import main
from sqlbuild.compiler.compile._helpers.analysis import compact
from sqlbuild.compiler.compile._helpers.analysis.compact import native_section
from sqlbuild.compiler.compile._helpers.assembly import binding_waves
from sqlbuild.compiler.compile._helpers.assembly import project as project_assembly
from sqlbuild.compiler.compile._helpers.assembly.binding_waves import analyze_binding_waves
from sqlbuild.compiler.compile.classes.binding_dataflow import BindingDataflow
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import (
    CompactBatchPreparation,
    CompileAdapterContext,
    CompileAuditInput,
    CompiledLineageColumnFact,
    CompiledModel,
    CompiledProject,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.manifest.main.build import build_manifest
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.main.project import compile_project
from sqlbuild.compiler.pipeline.models import CompilePipelineOptions, CompilePipelineResult
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.sql_values.types import CollectionRendering
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import (
    CompileOutcome,
    DataflowScheduleCase,
    SharedBindingQueryCase,
)

_SCHEMA_FIXTURE_PATH: Path = (
    Path(__file__).resolve().parents[5] / "fixtures" / "dbt_manifest_v12_schema.json"
)
_RESHAPED_STAR_PROJECT_TOML: str = 'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = []\n'
RESHAPED_STAR_UPSTREAM_MODELS: dict[str, str] = {
    "staged_orders": "SELECT 1 AS customer_id, 'books' AS category, 10 AS amount",
    "wide_orders": "SELECT 1 AS customer_id, 2 AS books, 3 AS games",
}
_ANALYSIS_THREAD_NAME: str = "sqlbuild-analys"
_MODEL_ANALYSIS_THREAD_PREFIX: str = "sqlbuild-model-analysis-"
_HOLD_SECONDS: float = 0.3
_REACQUIRE_DELAY_SECONDS: float = 0.05
_INTERRUPT_TIMEOUT_SECONDS: float = 30.0
_INTERRUPT_DELAY_SECONDS: float = 0.15
_SEMANTIC_BINDING_PROJECT_TOML: str = 'name = "semantic_binding"\nadapter = "duckdb"\n'
_AUDIT_FACTORY_ADAPTER_CONTEXT: CompileAdapterContext = CompileAdapterContext(
    value_renderer=DuckDbAdapter(),
    collection_rendering=CollectionRendering.VALUE_LIST,
    python_functions_inherit_default_namespace=True,
    sql_lexical_syntax=DuckDbAdapter.sql_lexical_syntax,
)


def compile_audits_for_project(*, project_dir: Path) -> tuple[CompileAuditInput, ...]:
    """Compile one project's audit inputs with the real DuckDB compiler path."""

    return build_compile_inputs(
        discovered_inputs=discover_project_inputs(project_dir=project_dir),
        adapter_context=_AUDIT_FACTORY_ADAPTER_CONTEXT,
        run_id="integration_run",
    ).audit_inputs


def audit_input_projection(
    *, audits: tuple[CompileAuditInput, ...]
) -> tuple[tuple[object, ...], ...]:
    """Project attachment-relevant fields for direct/generated equivalence."""

    return tuple(
        (
            audit.name,
            audit.audit_file.relative_path,
            audit.sql_body,
            audit.attached_target_kind,
            audit.attached_target_name,
            audit.attached_column_name,
            audit.severity,
            audit.run_scope,
            audit.always_run,
        )
        for audit in audits
    )


def run_compile_pipeline_for_project(
    *,
    project_dir: Path,
    adapter: BaseAdapter,
    defer_to: str | None = None,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    on_progress: Callable[[str], None] | None = None,
    resolve_python_run_selectors: bool = False,
) -> CompilePipelineResult:
    """Discover a project and run the real compile pipeline."""

    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    return run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        options=CompilePipelineOptions(
            no_sql_validation=True,
            defer_to=defer_to,
            select=select,
            exclude=exclude,
            resolve_python_run_selectors=resolve_python_run_selectors,
        ),
        hooks=ConnectionHooks(on_progress=on_progress),
    )


def build_manifest_for_pipeline_result(
    *,
    result: CompilePipelineResult,
    project_name: str,
    adapter_type: str,
) -> dict[str, object]:
    """Build the manifest artifact from a compile pipeline result."""

    return build_manifest(
        project=result.project,
        plan_output=result.plan_output,
        project_name=project_name,
        adapter_type=adapter_type,
        upstream_deps=result.plan_output.upstream_deps,
        downstream_deps=result.plan_output.downstream_deps,
    )


def validate_manifest_against_dbt_schema(manifest: dict[str, object]) -> None:
    """Validate a manifest dict against the dbt v12 JSON schema."""

    from jsonschema import Draft202012Validator

    schema: dict[str, Any] = json.loads(_SCHEMA_FIXTURE_PATH.read_text(encoding="utf-8"))
    validator: Any = Draft202012Validator(schema)
    errors: list[str] = [e.message for e in validator.iter_errors(manifest)]
    assert errors == [], f"Manifest schema validation errors: {errors}"


def write_semantic_binding_project(
    *, project_dir: Path, upstream_sql: str, downstream_sql: str
) -> None:
    _ = (project_dir / "sqlbuild_project.toml").write_text(
        _SEMANTIC_BINDING_PROJECT_TOML, encoding="utf-8"
    )
    models_dir: Path = project_dir / "models"
    models_dir.mkdir()
    _ = (models_dir / "upstream.sql").write_text(upstream_sql, encoding="utf-8")
    _ = (models_dir / "downstream.sql").write_text(downstream_sql, encoding="utf-8")


def compile_reshaped_star_model(
    *, project_dir: Path, query_sql: str
) -> tuple[CompiledProject, CompiledModel]:
    """Compile one reshaped-star model over the shared upstream order models."""

    (project_dir / "sqlbuild_project.toml").write_text(
        _RESHAPED_STAR_PROJECT_TOML, encoding="utf-8"
    )
    models: Path = project_dir / "models"
    models.mkdir()
    for name, sql in RESHAPED_STAR_UPSTREAM_MODELS.items():
        (models / f"{name}.sql").write_text(
            f"MODEL (description 'Test model.', materialized table);\n{sql}", encoding="utf-8"
        )
    (models / "reshaped_orders.sql").write_text(
        f"MODEL (description 'Test model reshaped_orders.', materialized table);\n{query_sql}",
        encoding="utf-8",
    )
    project: CompiledProject = compile_project(
        discovered_inputs=discover_project_inputs(project_dir=project_dir),
        adapter=DuckDbAdapter(),
    )
    models_by_name: dict[str, CompiledModel] = {model.name: model for model in project.models}
    return project, models_by_name["reshaped_orders"]


def lineage_source_pairs(column: CompiledLineageColumnFact) -> frozenset[tuple[str, str]]:
    """Return one lineage column's upstream (resource, column) pairs."""

    return frozenset(
        (source.resource_name, source.column_name) for source in column.upstream_columns
    )


_SHARED_BINDING_UPSTREAM_SQL: str = (
    "MODEL (description 'Test model.', materialized view); SELECT 1 AS id, 2.5 AS amount"
)


def write_shared_binding_project(*, project_dir: Path, test_case: SharedBindingQueryCase) -> None:
    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = []\n'
    )
    models: Path = project_dir / "models"
    models.mkdir()
    (models / "orders.sql").write_text(_SHARED_BINDING_UPSTREAM_SQL)
    (models / "customers.sql").write_text(_SHARED_BINDING_UPSTREAM_SQL)
    (models / "orders_summary.sql").write_text(test_case.orders_summary_sql)
    (models / "customers_summary.sql").write_text(test_case.customers_summary_sql)
    for name, sql in test_case.later_models:
        (models / f"{name}.sql").write_text(sql)


def trace_native_compact_batches(monkeypatch: pytest.MonkeyPatch) -> list[CompactBatchPreparation]:
    original: Callable[..., object] = compact._run_compact_analysis_batch
    preparations: list[CompactBatchPreparation] = []

    def traced(*, preparation: CompactBatchPreparation) -> object:
        preparations.append(preparation)
        return original(preparation=preparation)

    monkeypatch.setattr(compact, "_run_compact_analysis_batch", traced)
    return preparations


def apply_warehouse_setup_sql(*, project_dir: Path, statements: tuple[str, ...]) -> None:
    """Create pre-existing warehouse objects in the project's file-backed DuckDB database."""

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(project_dir / "warehouse.duckdb"))
    try:
        statement: str
        for statement in statements:
            connection.execute(statement)
    finally:
        connection.close()


def reshape_random_dag_model(*, project_dir: Path, name: str) -> None:
    """Add one leading output column, changing the model's published shape signature."""

    path: Path = project_dir / "models" / f"{name}.sql"
    header, body = path.read_text(encoding="utf-8").split("\n", 1)
    path.write_text(
        f"{header}\nSELECT CAST(7 AS INTEGER) AS reshaped, *\n"
        f"FROM ({body.strip()}) AS reshaped_input\n",
        encoding="utf-8",
    )


def compile_outcome(
    *, project_dir: Path, args: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> CompileOutcome:
    """Compile through the CLI; return the exit code, timing-free JSON, and artifacts."""

    exit_code: int = main(["--project-dir", str(project_dir), "compile", "--json", *args])
    payload: dict[str, object] = json.loads(
        capsys.readouterr().out.replace(str(project_dir), "<project>")
    )
    _ = payload.pop("compile_timings", None)
    compiled: Path = project_dir / "target" / "compiled"
    return (
        exit_code,
        payload,
        {
            path.relative_to(compiled).as_posix(): path.read_bytes()
            for path in compiled.rglob("*.sql")
        },
    )


def reshape_models(*, project_dir: Path, names: tuple[str, ...], indexes: tuple[int, ...]) -> None:
    """Reshape the models at `indexes` of the generated topological name order."""

    for index in indexes:
        reshape_random_dag_model(project_dir=project_dir, name=names[index])


def use_wave_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Analyze one topological level at a time, the reference schedule."""

    monkeypatch.setattr(project_assembly, "analyze_binding_dataflow", analyze_binding_waves)


def perturb_dataflow_schedule(
    *, monkeypatch: pytest.MonkeyPatch, case: DataflowScheduleCase, seed: int
) -> None:
    """Change worker count and batch size, and delay native completions at random."""

    rng: random.Random = random.Random(seed)
    original: Callable[..., object] = compact._run_compact_analysis_batch

    def delayed(*, preparation: CompactBatchPreparation) -> object:
        result: object = original(preparation=preparation)
        with native_section():
            time.sleep(rng.random() * case.max_delay_seconds)
        return result

    monkeypatch.setattr(binding_waves, "_DATAFLOW_WORKERS", case.workers)
    monkeypatch.setattr(binding_waves, "_DATAFLOW_BATCH_MIN", 1)
    monkeypatch.setattr(binding_waves, "_DATAFLOW_BATCH_LIMIT", case.batch_limit)
    monkeypatch.setattr(compact, "_run_compact_analysis_batch", delayed)


def fail_model_analysis(*, monkeypatch: pytest.MonkeyPatch, model_names: tuple[str, ...]) -> None:
    """Raise from analysis of a batch holding a named model, as an internal fault would."""

    original: Callable[..., tuple[Any, ...]] = project_assembly._analyze_model_sql_requests
    failing_names: frozenset[str] = frozenset(model_names)

    def failing(**kwargs: Any) -> tuple[Any, ...]:
        batch_names: set[str] = {
            request.model_input.model_file.file_path.stem for request in kwargs["requests"]
        }
        for name in sorted(batch_names & failing_names)[:1]:
            _raise_analysis_fault(name)
        return original(**kwargs)

    monkeypatch.setattr(project_assembly, "_analyze_model_sql_requests", failing)


def _raise_analysis_fault(name: str) -> None:
    raise RuntimeError(f"analysis fault in {name}")


def analysis_pool_thread_ids(monkeypatch: pytest.MonkeyPatch) -> list[set[str]]:
    """Record native analysis threads now, then again after each compact batch."""

    original: Callable[..., object] = compact._run_compact_analysis_batch
    observed: list[set[str]] = [_analysis_thread_ids()]

    def traced(*, preparation: CompactBatchPreparation) -> object:
        result: object = original(preparation=preparation)
        observed.append(_analysis_thread_ids())
        return result

    monkeypatch.setattr(compact, "_run_compact_analysis_batch", traced)
    return observed


def _analysis_thread_ids() -> set[str]:
    threads_by_name: dict[str, set[str]] = {}
    for task in Path("/proc/self/task").iterdir():
        with suppress(OSError):
            name: str = (task / "comm").read_text(encoding="utf-8").strip()
            threads_by_name.setdefault(name, set()).add(task.name)
    return threads_by_name.get(_ANALYSIS_THREAD_NAME, set())


def interrupt_reacquiring_analysis(*, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Send SIGINT while a worker thread holds the analysis lock and others reacquire it.

    Return overlaps, which name any batch that entered Python analysis while another held it.
    """

    original: Callable[..., object] = compact._run_compact_analysis_batch
    holder: threading.Event = threading.Event()
    owner: list[str] = []
    overlaps: list[str] = []
    worker_calls: itertools.count[int] = itertools.count()
    hold_calls: dict[bool, Callable[[], int]] = {
        False: lambda: next(worker_calls),
        True: lambda: -1,
    }

    def guarded(*, preparation: CompactBatchPreparation) -> object:
        overlaps.extend(owner)
        owner.append(threading.current_thread().name)
        call: int = hold_calls[threading.current_thread() is threading.main_thread()]()
        {0: _hold_analysis_lock}.get(call, _skip_hold)(holder)
        owner.clear()
        result: object = original(preparation=preparation)
        with native_section():
            time.sleep(_REACQUIRE_DELAY_SECONDS)
        return result

    def interrupt() -> None:
        _ = holder.wait(_INTERRUPT_TIMEOUT_SECONDS)
        time.sleep(_INTERRUPT_DELAY_SECONDS)
        signal.pthread_kill(threading.main_thread().ident or 0, signal.SIGINT)

    monkeypatch.setattr(binding_waves, "_DATAFLOW_BATCH_MIN", 1)
    monkeypatch.setattr(binding_waves, "_DATAFLOW_BATCH_LIMIT", 1)
    monkeypatch.setattr(compact, "_run_compact_analysis_batch", guarded)
    threading.Thread(target=interrupt, daemon=True).start()
    return overlaps


def _hold_analysis_lock(holder: threading.Event) -> None:
    holder.set()
    time.sleep(_HOLD_SECONDS)


def _skip_hold(holder: threading.Event) -> None:
    del holder


def interrupt_after_analysis_fault(
    *, monkeypatch: pytest.MonkeyPatch, failing_model: str, interrupted_model: str
) -> list[int]:
    """Fail one batch, then interrupt a batch that started beside it; return wave replays."""

    original: Callable[..., tuple[Any, ...]] = project_assembly._analyze_model_sql_requests
    actions: dict[str, Callable[[str], None]] = {
        failing_model: _fail_after_native_delay,
        interrupted_model: _interrupt_after_native_delay,
    }
    replays: list[int] = []
    analyze_waves: Callable[..., Any] = BindingDataflow.analyze_waves

    def failing(**kwargs: Any) -> tuple[Any, ...]:
        batch_names: set[str] = {
            request.model_input.model_file.file_path.stem for request in kwargs["requests"]
        }
        for name in sorted(batch_names & actions.keys()):
            actions[name](name)
        return original(**kwargs)

    def replay(self: BindingDataflow) -> Any:
        replays.append(1)
        return analyze_waves(self)

    monkeypatch.setattr(binding_waves, "_DATAFLOW_BATCH_MIN", 1)
    monkeypatch.setattr(binding_waves, "_DATAFLOW_BATCH_LIMIT", 1)
    monkeypatch.setattr(project_assembly, "_analyze_model_sql_requests", failing)
    monkeypatch.setattr(BindingDataflow, "analyze_waves", replay)
    return replays


def _fail_after_native_delay(name: str) -> None:
    with native_section():
        time.sleep(_REACQUIRE_DELAY_SECONDS)
    raise RuntimeError(f"analysis fault in {name}")


def _interrupt_after_native_delay(name: str) -> None:
    with native_section():
        time.sleep(_HOLD_SECONDS)
    raise KeyboardInterrupt(name)


def fail_worker_start(
    *, monkeypatch: pytest.MonkeyPatch, failing_start: int, interrupt_after_start: bool
) -> list[str]:
    """Fail one analysis worker start; return the names of analysis batches' threads.

    The failing start either never starts its thread or starts it and is then interrupted.
    """

    original_start: Callable[[threading.Thread], None] = threading.Thread.start
    starts: itertools.count[int] = itertools.count()
    batches: list[str] = trace_analysis_threads(monkeypatch)

    def start_then_interrupt(thread: threading.Thread) -> None:
        original_start(thread)
        raise KeyboardInterrupt(thread.name)

    failing: Callable[[threading.Thread], None] = {
        False: _refuse_start,
        True: start_then_interrupt,
    }[interrupt_after_start]

    def counted_start(thread: threading.Thread) -> None:
        {failing_start: failing}.get(next(starts), original_start)(thread)

    def start(thread: threading.Thread) -> None:
        {True: counted_start, False: original_start}[
            thread.name.startswith(_MODEL_ANALYSIS_THREAD_PREFIX)
        ](thread)

    monkeypatch.setattr(binding_waves, "_DATAFLOW_BATCH_MIN", 1)
    monkeypatch.setattr(binding_waves, "_DATAFLOW_BATCH_LIMIT", 1)
    monkeypatch.setattr(threading.Thread, "start", start)
    return batches


def _refuse_start(thread: threading.Thread) -> None:
    raise RuntimeError(f"cannot start {thread.name}")


def trace_analysis_threads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record the thread that runs each compact analysis batch, slowed to overlap batches."""

    original: Callable[..., object] = compact._run_compact_analysis_batch
    threads: list[str] = []

    def traced(*, preparation: CompactBatchPreparation) -> object:
        threads.append(threading.current_thread().name)
        with native_section():
            time.sleep(_REACQUIRE_DELAY_SECONDS)
        return original(preparation=preparation)

    monkeypatch.setattr(compact, "_run_compact_analysis_batch", traced)
    return threads


def live_model_analysis_threads() -> list[str]:
    """Return model analysis worker threads that are still alive."""

    names_by_kind: dict[bool, list[str]] = {}
    for thread in threading.enumerate():
        names_by_kind.setdefault(thread.name.startswith(_MODEL_ANALYSIS_THREAD_PREFIX), []).append(
            thread.name
        )
    return sorted(names_by_kind.get(True, []))
