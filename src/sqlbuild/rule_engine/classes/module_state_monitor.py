"""Exact per-rule module-state change detection with one shared snapshot per check."""

from __future__ import annotations

from itertools import chain
from pathlib import Path

from sqlbuild.rule_engine._helpers.host.module_state import (
    module_state_fingerprint,
    module_state_snapshot,
    rules_root_prefix,
)
from sqlbuild.rule_engine.exceptions import OpaqueModuleStateError
from sqlbuild.rule_engine.models import ModuleStateFingerprint, ModuleStateTrace

_EMPTY_TRACE: ModuleStateTrace = ModuleStateTrace(
    touched={}, descended_types=frozenset(), checked_instances=frozenset()
)


class ModuleStateMonitor:
    """Report rule codes whose module-state fingerprint differs from when monitoring started."""

    def __init__(
        self, *, namespaces: dict[str, tuple[dict[str, object], ...]], rules_root: Path
    ) -> None:
        self._rules_root: str = rules_root_prefix(rules_root)
        self._namespaces: dict[str, tuple[dict[str, object], ...]] = namespaces
        self._trace: ModuleStateTrace = _EMPTY_TRACE
        states: dict[str, ModuleStateFingerprint | None] = self._fingerprints(tuple(namespaces))
        self._initial: dict[str, str] = {
            code: state.token for code, state in states.items() if state is not None
        }
        self._unobservable: tuple[str, ...] = tuple(
            code for code, state in states.items() if state is None
        )
        self._baseline: list[object] | None = self._verified_snapshot(states)

    def changed_codes(self) -> tuple[str, ...]:
        """Return codes whose module state changed since monitoring started, each only once."""

        changed: list[str] = list(self._unobservable)
        self._unobservable = ()
        if not self._initial:
            return tuple(changed)
        if self._baseline is not None and self._snapshot() == self._baseline:
            return tuple(changed)
        states: dict[str, ModuleStateFingerprint | None] = self._fingerprints(tuple(self._initial))
        for code, state in states.items():
            if state is None or state.token != self._initial[code]:
                changed.append(code)
                del self._initial[code]
        self._baseline = self._verified_snapshot(states)
        return tuple(changed)

    def _fingerprints(self, codes: tuple[str, ...]) -> dict[str, ModuleStateFingerprint | None]:
        by_namespaces: dict[tuple[int, ...], ModuleStateFingerprint | None] = {}
        states: dict[str, ModuleStateFingerprint | None] = {}
        for code in codes:
            namespaces: tuple[dict[str, object], ...] = self._namespaces[code]
            key: tuple[int, ...] = tuple(map(id, namespaces))
            if key not in by_namespaces:
                try:
                    by_namespaces[key] = module_state_fingerprint(
                        namespaces=namespaces, rules_root=self._rules_root
                    )
                except OpaqueModuleStateError:
                    by_namespaces[key] = None
            states[code] = by_namespaces[key]
        return states

    def _verified_snapshot(
        self, states: dict[str, ModuleStateFingerprint | None]
    ) -> list[object] | None:
        traces: tuple[ModuleStateTrace, ...] = tuple(
            state.trace
            for code, state in states.items()
            if state is not None and code in self._initial
        )
        self._trace = ModuleStateTrace(
            touched=dict(chain.from_iterable(trace.touched.items() for trace in traces)),
            descended_types=frozenset(
                chain.from_iterable(trace.descended_types for trace in traces)
            ),
            checked_instances=frozenset(
                chain.from_iterable(trace.checked_instances for trace in traces)
            ),
        )
        return self._snapshot()

    def _snapshot(self) -> list[object] | None:
        try:
            return module_state_snapshot(
                namespaces=chain.from_iterable(map(self._namespaces.__getitem__, self._initial)),
                rules_root=self._rules_root,
                trace=self._trace,
                walks=len(self._initial),
            )
        except Exception:
            return None
