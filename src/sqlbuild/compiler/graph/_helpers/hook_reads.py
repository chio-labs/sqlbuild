"""Ordering edges from the resources model hooks read."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.types import CompiledModelView, CompiledProjectView
from sqlbuild.compiler.discovery.models import PythonHookEntry, SqlHookEntry
from sqlbuild.compiler.graph._helpers.sql_refs import sql_ref_key_impl
from sqlbuild.compiler.graph.models import HookReadEdge
from sqlbuild.compiler.graph.types import HookReadType
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


def hook_read_edges_impl(*, project: CompiledProjectView) -> tuple[HookReadEdge, ...]:
    """Return edges from each hook read to the model that runs the hook."""

    reads_by_hook: dict[str, tuple[SqlResourceRef, ...]] = {
        hook.name: hook.reads for hook in project.hook_functions if hook.reads
    }
    paths_by_hook: dict[str, Path] = {
        hook.name: hook.relative_path for hook in project.hook_functions
    }
    candidates: list[HookReadEdge] = []
    for model in project.models:
        for hook_name in model_python_hook_names_impl(model):
            candidates.extend(
                HookReadEdge(
                    hook_name=hook_name,
                    gated=model.key,
                    read=sql_ref_key_impl(ref),
                    hook_path=paths_by_hook.get(hook_name),
                )
                for ref in reads_by_hook.get(hook_name, ())
            )
        candidates.extend(_sql_hook_read_edges(model))
    return tuple(dict.fromkeys(edge for edge in candidates if edge.read != edge.gated))


def _sql_hook_read_edges(model: CompiledModelView) -> tuple[HookReadEdge, ...]:
    edges: list[HookReadEdge] = []
    for hook_key in _MODEL_HOOK_KEYS:
        entries: object = model.config.values.get(hook_key)
        items: tuple[object, ...] = (
            tuple(entries) if isinstance(entries, list | tuple) else (entries,)
        )
        for index, entry in enumerate(items):
            if not isinstance(entry, SqlHookEntry) or not entry.reads:
                continue
            named: bool = entry.name is not None
            edges.extend(
                HookReadEdge(
                    hook_name=entry.name if entry.name is not None else f"{hook_key}[{index}]",
                    gated=model.key,
                    read=sql_ref_key_impl(ref),
                    hook_type=HookReadType.SQL if named else HookReadType.INLINE_SQL,
                    hook_path=entry.relative_path or model.relative_path,
                )
                for ref in entry.reads
            )
    return tuple(edges)
