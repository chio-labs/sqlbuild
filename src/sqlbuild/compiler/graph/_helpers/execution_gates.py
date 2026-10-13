"""Ordering edges attached audits and model hooks add, computed natively from project facts."""

from __future__ import annotations

from itertools import chain
from pathlib import Path

import orjson

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    CompiledAuditView,
    CompiledModelView,
    CompiledProjectView,
    CompiledResourceType,
)
from sqlbuild.compiler.discovery.models import PythonHookEntry, SqlHookEntry
from sqlbuild.compiler.graph.models import AttachedAuditGateEdge, HookReadEdge
from sqlbuild.compiler.graph.types import HookReadType, NativeKey
from sqlbuild.python_nodes.models import SqlResourceRef

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

    gates, _ = _native.native_execution_gate_edges(_request(project))
    return tuple(
        AttachedAuditGateEdge(
            audit_name=audit_name, target=_key(target), gated=_key(gated), read=_key(read)
        )
        for audit_name, target, gated, read in gates
    )


def hook_read_edges_impl(*, project: CompiledProjectView) -> tuple[HookReadEdge, ...]:
    """Return edges from each hook read to the model that runs the hook."""

    _, hooks = _native.native_execution_gate_edges(_request(project))
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


def _request(project: CompiledProjectView) -> str:
    return orjson.dumps(
        {
            "resources": [
                {"key": model.key_row, "deps": model.dep_rows} for model in project.models
            ],
            "models": [_model_row(model) for model in project.models],
            "audits": [_audit_row(audit) for audit in project.audits],
            "hooks": [
                {
                    "name": hook.name,
                    "path": hook.relative_path.as_posix(),
                    "reads": _ref_rows(hook.reads),
                }
                for hook in project.hook_functions
            ],
        }
    ).decode()


def _model_row(model: CompiledModelView) -> dict[str, object]:
    return {
        "name": model.name,
        "path": str(model.relative_path),
        "python_hooks": list(model_python_hook_names_impl(model)),
        "sql_hooks": list(
            chain.from_iterable(
                _sql_hook_rows(hook_key=hook_key, entries=model.config.values.get(hook_key))
                for hook_key in _MODEL_HOOK_KEYS
            )
        ),
    }


def _sql_hook_rows(*, hook_key: str, entries: object) -> list[dict[str, object]]:
    items: tuple[object, ...] = tuple(entries) if isinstance(entries, list | tuple) else (entries,)
    return [
        {
            "hook_key": hook_key,
            "index": index,
            "name": entry.name,
            "path": None if entry.relative_path is None else str(entry.relative_path),
            "reads": _ref_rows(entry.reads),
        }
        for index, entry in enumerate(items)
        if isinstance(entry, SqlHookEntry) and entry.reads
    ]


def _audit_row(audit: CompiledAuditView) -> dict[str, object]:
    target: tuple[str, str] | None = (
        (
            str(AttachedAuditTargetKind(audit.attached_target_kind).resource_type),
            audit.attached_target_name,
        )
        if audit.attached_target_kind is not None and audit.attached_target_name is not None
        else None
    )
    return {
        "name": audit.name,
        "path": "",
        "target": target,
        "scope_deps": [(str(key.resource_type), key.name) for key in audit.scope_deps],
    }


def _ref_rows(refs: tuple[SqlResourceRef, ...]) -> list[tuple[str, str]]:
    return [(str(ref.kind), ref.name) for ref in refs]
