"""Reuse model attachment results across compile invocations."""

from __future__ import annotations

import gc
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
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
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile
from sqlbuild.compiler.fact_cache.classes.fact_cache_store import FactCacheStore
from sqlbuild.compiler.profiling.main._metric import record_compile_metric

_DETACHED_MODEL_FILE: DiscoveredSqlModelFile = DiscoveredSqlModelFile(
    file_path=Path(),
    relative_path=Path(),
    contents="",
    header_values={},
    header_column_locations={},
    output_column_locations={},
    query_sql="",
)


@contextmanager
def _collection_paused() -> Iterator[None]:
    """Pause cyclic garbage collection while thousands of acyclic cached facts are unpickled."""

    collecting: bool = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if collecting:
            gc.enable()


class ModelAttachmentCache:
    """Store one attachment fact per model; models that read per-run values are recomputed."""

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
        self._bypasses: int = 0

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
                record_compile_metric(metric="attachment_cache_bypasses", value=self._bypasses)

    def read(self, entries: Sequence[tuple[str, str]]) -> dict[str, ModelAttachmentFact]:
        """Return verified facts by key for requested (slot, key) pairs."""

        with _collection_paused():
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
                self._bypasses += 1
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
    ) -> None:
        """Queue one freshly attached model for publication after a successful compile."""

        if self.environment is None:
            return
        volatile: bool = not reads <= self.environment.keyed_reads
        self.store.stage(
            key=key,
            slot=slot,
            value=(
                ModelAttachmentFact(model_input=None)
                if volatile
                else ModelAttachmentFact(
                    model_input=replace(model_input, model_file=_DETACHED_MODEL_FILE),
                    hook_references=hook_references,
                    diagnostics=() if diagnostics is None else diagnostics.entries,
                )
            ),
        )
