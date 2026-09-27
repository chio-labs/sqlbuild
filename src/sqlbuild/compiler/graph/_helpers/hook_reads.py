"""Ordering edges from the resources Python hooks declare they read."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledModel, CompiledObjectKey, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import PythonHookEntry
from sqlbuild.compiler.graph._helpers.algorithms import transitive_closure_many_impl
from sqlbuild.compiler.graph._helpers.audit_gates import attached_audit_gate_edges_impl
from sqlbuild.compiler.graph._helpers.lineage import build_lineage_upstream_deps_impl
from sqlbuild.compiler.graph.models import HookReadEdge
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind

_MODEL_HOOK_KEYS: tuple[str, ...] = ("pre_hooks", "post_hooks")
_RESOURCE_TYPE_BY_REF_KIND: dict[SqlResourceRefKind, CompiledResourceType] = {
    SqlResourceRefKind.MODEL: CompiledResourceType.MODEL,
    SqlResourceRefKind.SOURCE: CompiledResourceType.SOURCE,
    SqlResourceRefKind.SEED: CompiledResourceType.SEED,
}


def hook_read_key(ref: SqlResourceRef) -> CompiledObjectKey:
    """Return the compiled graph key a declared hook read names."""

    return CompiledObjectKey(resource_type=_RESOURCE_TYPE_BY_REF_KIND[ref.kind], name=ref.name)


def model_python_hook_names_impl(model: CompiledModel) -> tuple[str, ...]:
    """Return the Python hooks attached to one model, in lifecycle order."""

    names: list[str] = []
    for hook_key in _MODEL_HOOK_KEYS:
        entries: object = model.config.values.get(hook_key)
        if isinstance(entries, PythonHookEntry):
            names.append(entries.name)
        elif isinstance(entries, list | tuple):
            names.extend(entry.name for entry in entries if isinstance(entry, PythonHookEntry))
    return tuple(dict.fromkeys(names))


def hook_read_edges_impl(*, project: CompiledProject) -> tuple[HookReadEdge, ...]:
    """Return edges from each declared hook read to the model that runs the hook."""

    reads_by_hook: dict[str, tuple[SqlResourceRef, ...]] = {
        hook.name: hook.reads for hook in project.hook_functions if hook.reads
    }
    if not reads_by_hook:
        return ()
    edges: dict[HookReadEdge, None] = {}
    for model in project.models:
        for hook_name in model_python_hook_names_impl(model):
            for ref in reads_by_hook.get(hook_name, ()):
                read: CompiledObjectKey = hook_read_key(ref)
                if read != model.key:
                    edges[HookReadEdge(hook_name=hook_name, gated=model.key, read=read)] = None
    return tuple(edges)


def hook_read_cycle_impl(*, project: CompiledProject) -> HookReadEdge | None:
    """Return the first declared hook read that depends on the model running the hook."""

    edges: tuple[HookReadEdge, ...] = hook_read_edges_impl(project=project)
    if not edges:
        return None
    upstream: dict[CompiledObjectKey, list[CompiledObjectKey]] = {
        key: list(deps) for key, deps in build_lineage_upstream_deps_impl(project).items()
    }
    for gate in attached_audit_gate_edges_impl(project=project):
        upstream.setdefault(gate.gated, []).append(gate.read)
    for edge in edges:
        upstream.setdefault(edge.gated, []).append(edge.read)
    for edge in sorted(edges, key=lambda item: (item.gated.name, item.hook_name, item.read.name)):
        if edge.gated in transitive_closure_many_impl(
            starts=(edge.read,), edges=upstream, include_starts=False
        ):
            return edge
    return None
