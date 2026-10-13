"""Ordering edges attached audits and model hooks add, computed natively from project facts."""

from __future__ import annotations

from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import (
    CompiledModelView,
    CompiledProjectView,
    CompiledResourceType,
)
from sqlbuild.compiler.discovery.models import PythonHookEntry
from sqlbuild.compiler.graph.models import AttachedAuditGateEdge, HookReadEdge
from sqlbuild.compiler.graph.types import HookReadType, NativeKey

_MODEL_HOOK_KEYS: tuple[str, ...] = ("pre_hooks", "post_hooks")


def model_python_hook_names_impl(model: CompiledModelView) -> tuple[str, ...]:
    """Return the Python hooks attached to one model, in lifecycle order."""

    names: list[str] = []
    for hook_key in _MODEL_HOOK_KEYS:
        entries: object = model.config.values.get(hook_key)
        if isinstance(entries, PythonHookEntry):
            names.append(entries.name)
        elif isinstance(entries, list | tuple):
            names.extend(entry.name for entry in entries if isinstance(entry, PythonHookEntry))
    return tuple(dict.fromkeys(names))


def attached_audit_gate_edges_impl(
    *, project: CompiledProjectView
) -> tuple[AttachedAuditGateEdge, ...]:
    """Return edges from each extra audit read to its model or seed target, or source triggers."""

    gates, _ = _native.native_execution_gate_edges(project)
    return tuple(
        AttachedAuditGateEdge(
            audit_name=audit_name, target=_key(target), gated=_key(gated), read=_key(read)
        )
        for audit_name, target, gated, read in gates
    )


def hook_read_edges_impl(*, project: CompiledProjectView) -> tuple[HookReadEdge, ...]:
    """Return edges from each hook read to the model that runs the hook."""

    _, hooks = _native.native_execution_gate_edges(project)
    return tuple(
        HookReadEdge(
            hook_name=hook_name,
            gated=_key(gated),
            read=_key(read),
            hook_type=HookReadType(hook_type),
            hook_path=None if path is None else Path(path),
        )
        for hook_name, gated, read, hook_type, path in hooks
    )


def _key(pair: NativeKey) -> CompiledObjectKey:
    return CompiledObjectKey(resource_type=CompiledResourceType(pair[0]), name=pair[1])
