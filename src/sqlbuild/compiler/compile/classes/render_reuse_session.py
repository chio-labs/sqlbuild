"""Reuse unaffected rendered inputs from the previous compile and record this compile's."""

from __future__ import annotations

import pickle
import threading
from collections.abc import Callable
from dataclasses import replace
from typing import cast

from sqlbuild.compiler.compile._helpers.diagnostics.collector import (
    report_compile_diagnostic,
    tapped_compile_diagnostics,
)
from sqlbuild.compiler.compile.classes.compile_input_reads import CompileInputReads
from sqlbuild.compiler.compile.constants import (
    COMPILE_INPUT_READS,
    RENDER_REUSE_MODEL_AUDITS_PREFIX,
)
from sqlbuild.compiler.compile.models import (
    CompileAuditInput,
    CompileModelInput,
    CompilerDiagnostic,
    RenderReuseState,
    StoredRender,
)
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile
from sqlbuild.compiler.fact_cache.exceptions import FactCachePayloadError
from sqlbuild.compiler.fact_cache.main._dump_fact_payload import dumped_fact_payload
from sqlbuild.compiler.fact_cache.main._load_fact_payload import loaded_fact_payload
from sqlbuild.compiler.profiling.main._metric import record_compile_metric

_LOAD_ERRORS: tuple[type[Exception], ...] = (
    FactCachePayloadError,
    pickle.UnpicklingError,
    AttributeError,
    EOFError,
    ImportError,
    IndexError,
    KeyError,
    TypeError,
    ValueError,
    RecursionError,
    MemoryError,
    OverflowError,
)


class CompileRenderReuseSession:
    """Serve stored renders of inputs a change set cannot affect, and record every render."""

    def __init__(
        self,
        *,
        prior: RenderReuseState | None,
        changed_paths: frozenset[str] | None,
        retained_models: frozenset[str] = frozenset(),
        retained_groups: frozenset[str] = frozenset(),
    ) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._claimed: bool = False
        self._prior: RenderReuseState | None = prior if changed_paths is not None else None
        self._changed_paths: frozenset[str] = changed_paths or frozenset()
        self._reusable: bool = False
        self._model_paths: tuple[str, ...] | None = None
        self._retained_models: frozenset[str] = retained_models
        self._retained_groups: frozenset[str] = retained_groups
        self._model_records: dict[str, memoryview | None] = {}
        self._group_records: dict[str, memoryview | None] = {}
        self._decoded_models: dict[str, StoredRender] = {}
        self._decoded_groups: dict[str, StoredRender] = {}
        self._pending_models: list[tuple[str, StoredRender]] = []
        self._pending_groups: list[tuple[str, StoredRender]] = []
        self._serialized_models: dict[str, memoryview] = {}
        self._serialized_groups: dict[str, memoryview] = {}
        self._reused_paths: set[str] = set()

    def claim(self) -> bool:
        """Return True for the first claim only; later project renders neither reuse nor record."""

        with self._lock:
            claimed: bool = self._claimed
            self._claimed = True
            return not claimed

    def plan_models(self, *, model_files: tuple[DiscoveredSqlModelFile, ...]) -> None:
        """Reuse stored renders only when the change set touches nothing but existing models."""

        model_paths: tuple[str, ...] = tuple(str(item.relative_path) for item in model_files)
        self._model_paths = model_paths
        prior: RenderReuseState | None = self._prior
        self._reusable = (
            prior is not None
            and prior.model_paths == model_paths
            and self._changed_paths.issubset(model_paths)
        )

    def has_reusable_model(self, *, model_file: DiscoveredSqlModelFile) -> bool:
        """Return whether a stored render of this model may stand in for rendering it."""

        path: str = str(model_file.relative_path)
        return (
            self._reusable
            and self._prior is not None
            and path not in self._changed_paths
            and path in self._prior.model_payloads
        )

    def reused_model(self, *, model_file: DiscoveredSqlModelFile) -> CompileModelInput | None:
        """Return the stored render of an unchanged model, replaying what rendering reported."""

        if not self.has_reusable_model(model_file=model_file) or self._prior is None:
            return None
        path: str = str(model_file.relative_path)
        payload: memoryview | None = self._prior.model_payloads[path]
        stored: StoredRender | None = None if payload is None else _loaded_render(payload)
        if stored is None or not isinstance(stored.value, CompileModelInput):
            return None
        _replay(stored=stored)
        self._model_records[path] = payload
        self._decoded_models[path] = stored
        self._reused_paths.add(path)
        record_compile_metric(metric="render_reuse_hits", value=1)
        return replace(stored.value, model_file=model_file)

    def rendered_model(
        self,
        *,
        model_file: DiscoveredSqlModelFile,
        render: Callable[[], CompileModelInput],
    ) -> CompileModelInput:
        """Render one model and record its render with what rendering reported and read."""

        with (
            COMPILE_INPUT_READS.recording() as reads,
            tapped_compile_diagnostics() as reported,
        ):
            model_input: CompileModelInput = render()
        record_compile_metric(metric="render_reuse_misses", value=1)
        stored: StoredRender | None = _stored_render(
            reads=reads, value=replace(model_input, model_file=None), reported=reported
        )
        if stored is not None:
            self._pending_models.append((str(model_file.relative_path), stored))
        return model_input

    def model_audits(
        self,
        *,
        model_input: CompileModelInput,
        render: Callable[[], tuple[CompileAuditInput, ...]],
    ) -> tuple[CompileAuditInput, ...]:
        """Return a reused model's stored attached audits, or render and record them."""

        path: str = str(model_input.model_file.relative_path)
        return self.group(
            name=f"{RENDER_REUSE_MODEL_AUDITS_PREFIX}{path}",
            render=render,
            reusable=path in self._reused_paths,
        )

    def group[T](self, *, name: str, render: Callable[[], T], reusable: bool = True) -> T:
        """Return a stored project-wide render no model edit can affect, or render and record it."""

        payload: memoryview | None = (
            self._prior.group_payloads.get(name)
            if reusable and self._reusable and self._prior is not None
            else None
        )
        stored: StoredRender | None = None if payload is None else _loaded_render(payload)
        if stored is not None and payload is not None:
            _replay(stored=stored)
            self._group_records[name] = payload
            self._decoded_groups[name] = stored
            return cast(T, stored.value)
        with (
            COMPILE_INPUT_READS.recording() as reads,
            tapped_compile_diagnostics() as reported,
        ):
            value: T = render()
        rendered: StoredRender | None = _stored_render(reads=reads, value=value, reported=reported)
        if rendered is not None:
            self._pending_groups.append((name, rendered))
        return value

    def pending_renders(self) -> int:
        """Return how many new renders storing this compile still has to serialize."""

        return len(self._pending_models) + len(self._pending_groups)

    def reused_any(self) -> bool:
        """Return whether any render was reused, so imports it made were skipped this run."""

        return bool(self._decoded_models or self._decoded_groups)

    def release_stored(self) -> None:
        """Drop stored base bytes once every render is decoded, recording reused renders as None."""

        self._prior = None
        self._reusable = False
        for records, retained in (
            (self._model_records, self._retained_models),
            (self._group_records, self._retained_groups),
        ):
            for key in records.keys() - retained:
                records[key] = None

    def stored_state(self, *, complete: bool = False) -> RenderReuseState | None:
        """Serialize this compile's renders; with complete, re-serialize released reused ones."""

        if self._model_paths is None:
            return None
        self.release_stored()
        self._serialize_pending()
        if complete:
            self._model_records = _reserialized(
                records=self._model_records, decoded=self._decoded_models
            )
            self._group_records = _reserialized(
                records=self._group_records, decoded=self._decoded_groups
            )
        return RenderReuseState(
            model_paths=self._model_paths,
            model_payloads={**self._model_records, **self._serialized_models},
            group_payloads={**self._group_records, **self._serialized_groups},
        )

    def _serialize_pending(self) -> None:
        for pending, serialized in (
            (self._pending_models, self._serialized_models),
            (self._pending_groups, self._serialized_groups),
        ):
            for key, stored in pending:
                payload: bytes | None = _dumped(stored)
                if payload is not None:
                    serialized[key] = memoryview(payload)
            pending.clear()


def _reserialized(
    *, records: dict[str, memoryview | None], decoded: dict[str, StoredRender]
) -> dict[str, memoryview | None]:
    complete: dict[str, memoryview | None] = {}
    key: str
    payload: memoryview | None
    for key, payload in records.items():
        if payload is None:
            dumped: bytes | None = _dumped(decoded[key])
            if dumped is None:
                continue
            payload = memoryview(dumped)
        complete[key] = payload
    return complete


def _stored_render(
    *,
    reads: CompileInputReads,
    value: object,
    reported: list[tuple[tuple[str, ...], CompilerDiagnostic]],
) -> StoredRender | None:
    """Keep one render for reuse unless it read the run identity or provider settings."""

    if reads.read_run_id or reads.settings_classes:
        return None
    return StoredRender(
        value=value, diagnostics=tuple(reported), environment_names=reads.environment_names
    )


def _dumped(stored: StoredRender) -> bytes | None:
    try:
        return dumped_fact_payload(stored)
    except (pickle.PicklingError, TypeError, AttributeError, RecursionError):
        return None


def _replay(*, stored: StoredRender) -> None:
    for name in stored.environment_names:
        COMPILE_INPUT_READS.environment_read(name)
    for key, diagnostic in stored.diagnostics:
        report_compile_diagnostic(key=key, diagnostic=diagnostic)


def _loaded_render(payload: memoryview) -> StoredRender | None:
    try:
        loaded: object = loaded_fact_payload(payload)
    except _LOAD_ERRORS:
        return None
    return loaded if isinstance(loaded, StoredRender) else None
