"""Reuse model attachment results across compile invocations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from types import TracebackType

from sqlbuild.compiler.compile.classes.collected_compile_diagnostics import (
    CollectedCompileDiagnostics,
)
from sqlbuild.compiler.compile.constants import (
    MODEL_ATTACHMENT_FACT_ALGORITHM,
    MODEL_ATTACHMENT_FACT_CACHE_NAMESPACE,
)
from sqlbuild.compiler.compile.models import (
    CompileModelInput,
    CompileSqlReference,
    ModelAttachmentEnvironment,
    ModelAttachmentFact,
)
from sqlbuild.compiler.compile.types import ModelAttachmentBypass
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile
from sqlbuild.compiler.fact_cache.classes.fact_cache_store import FactCacheStore
from sqlbuild.compiler.profiling.main._metric import record_compile_metric
from sqlbuild.compiler.profiling.main.paused_cyclic_collection import paused_cyclic_collection

_DETACHED_MODEL_FILE: DiscoveredSqlModelFile = DiscoveredSqlModelFile(
    file_path=Path(),
    relative_path=Path(),
    contents="",
    header_values={},
    header_column_locations={},
    output_column_locations={},
    query_sql="",
)


class ModelAttachmentCache:
    """Reuse models that expanded macros, hooks, or declarations; mark the rest for recompute."""

    def __init__(
        self, *, root: Path | None, environment: ModelAttachmentEnvironment | None
    ) -> None:
        self.environment: ModelAttachmentEnvironment | None = environment
        self.store: FactCacheStore = FactCacheStore(
            root=root if environment is not None else None,
            namespace=MODEL_ATTACHMENT_FACT_CACHE_NAMESPACE,
            algorithm=MODEL_ATTACHMENT_FACT_ALGORITHM,
        )
        self._hits: int = 0
        self._misses: int = 0
        self._bypasses: dict[ModelAttachmentBypass, int] = dict.fromkeys(ModelAttachmentBypass, 0)

    def __enter__(self) -> ModelAttachmentCache:
        _ = self.store.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            self.store.__exit__(exc_type, exc_value, traceback)
        finally:
            if self.store.enabled:
                record_compile_metric(metric="attachment_cache_hits", value=self._hits)
                record_compile_metric(metric="attachment_cache_misses", value=self._misses)
                record_compile_metric(
                    metric="attachment_cache_bypasses",
                    value=self._bypasses[ModelAttachmentBypass.PER_RUN_VALUES],
                )
                record_compile_metric(
                    metric="attachment_cache_unexpanded_bypasses",
                    value=self._bypasses[ModelAttachmentBypass.UNEXPANDED],
                )

    def read(self, entries: Sequence[tuple[str, str]]) -> dict[str, ModelAttachmentFact]:
        """Return verified facts by key for requested (slot, key) pairs."""

        with paused_cyclic_collection():
            found: dict[str, object] = self.store.read_many(entries)
        return {
            key: value for key, value in found.items() if isinstance(value, ModelAttachmentFact)
        }

    def reuse(
        self, *, fact: ModelAttachmentFact | None, model_file: DiscoveredSqlModelFile
    ) -> CompileModelInput | None:
        """Return the cached model input rebound to the current file, or None to recompute."""

        if fact is None or fact.model_input is None:
            if fact is not None:
                self._bypasses[fact.bypass or ModelAttachmentBypass.PER_RUN_VALUES] += 1
            elif self.store.enabled:
                self._misses += 1
            return None
        self._hits += 1
        return replace(fact.model_input, model_file=model_file)

    def stage(
        self,
        *,
        slot: str,
        key: str,
        model_input: CompileModelInput,
        hook_references: tuple[CompileSqlReference, ...],
        reads: set[str],
        diagnostics: CollectedCompileDiagnostics | None,
        expanded: bool,
    ) -> None:
        """Queue one freshly attached model for publication after a successful compile."""

        if self.environment is None:
            return
        bypass: ModelAttachmentBypass | None = (
            ModelAttachmentBypass.PER_RUN_VALUES
            if not reads <= self.environment.keyed_reads
            else None
            if expanded
            else ModelAttachmentBypass.UNEXPANDED
        )
        self.store.stage(
            key=key,
            slot=slot,
            value=(
                ModelAttachmentFact(model_input=None, bypass=bypass)
                if bypass is not None
                else ModelAttachmentFact(
                    model_input=replace(model_input, model_file=_DETACHED_MODEL_FILE),
                    hook_references=hook_references,
                    diagnostics=() if diagnostics is None else diagnostics.entries,
                )
            ),
        )
