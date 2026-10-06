"""Read a bare `sqb scope` target name the way `sqb lineage` and `sqb rename` read targets."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.lineage.selection import resolve_lineage_target
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import LineageTarget
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.scopes.models import ResourceIdentity, ScopeLookup
from sqlbuild.compiler.scopes.types import ResourceKind

_KIND_SEPARATOR: str = ":"
_PATH_MARKERS: tuple[str, ...] = ("/", "\\", ".")
_BARE_RESOURCE_TYPES: dict[ResourceKind, CompiledResourceType] = {
    ResourceKind.MODEL: CompiledResourceType.MODEL,
    ResourceKind.SOURCE: CompiledResourceType.SOURCE,
    ResourceKind.SEED: CompiledResourceType.SEED,
    ResourceKind.FUNCTION: CompiledResourceType.UDF,
}
_BARE_USAGE: str = (
    "bare names work for models, sources, seeds and functions; write macros, enums, constants, "
    "tests and audits with their prefix, for example macro:<name>"
)


def qualify_scope_target(*, lookup: ScopeLookup, target: str | None) -> str | None:
    """Return `target` with its kind prefix when it is a bare model, source, seed or function."""

    if target is None or _KIND_SEPARATOR in target or any(m in target for m in _PATH_MARKERS):
        return target
    bare_matches: dict[str, ResourceIdentity] = {}
    identity: ResourceIdentity
    for identity in lookup.resources:
        if identity.kind in _BARE_RESOURCE_TYPES and identity.name == target:
            bare_matches[str(identity.kind)] = identity
    all_keys: dict[str, CompiledObjectKey] = {
        identity.name: CompiledObjectKey(
            resource_type=_BARE_RESOURCE_TYPES[identity.kind], name=identity.name
        )
        for identity in bare_matches.values()
    }
    resolved: LineageTarget = resolve_lineage_target(all_keys=all_keys, target=target)
    prefixed_matches: tuple[str, ...] = _prefix_required_matches(lookup=lookup, name=target)
    if resolved.key is None:
        if prefixed_matches:
            raise CliUserError(
                f"scope target '{target}' needs its prefix: {_or_list(prefixed_matches)}",
                code="C960",
                help=_BARE_USAGE,
            )
        raise CliUserError(f"unknown scope target '{target}'", code="C960", help=_BARE_USAGE)
    candidates: tuple[str, ...] = (
        *(f"{kind}:{target}" for kind in sorted(bare_matches)),
        *prefixed_matches,
    )
    if len(candidates) > 1:
        raise CliUserError(
            f"scope target '{target}' matches more than one resource or declaration; "
            f"write {_or_list(candidates)}",
            code="C960",
            help=_BARE_USAGE,
        )
    return candidates[0]


def _prefix_required_matches(*, lookup: ScopeLookup, name: str) -> tuple[str, ...]:
    resources: set[str] = {
        f"{identity.kind}:{name}"
        for identity in lookup.resources
        if identity.kind not in _BARE_RESOURCE_TYPES and identity.name == name
    }
    declarations: set[str] = {
        f"{identity.kind}:{name}"
        for identity in lookup.declarations
        if identity.owner is None and identity.name == name
    }
    return tuple(sorted(resources | declarations))


def _or_list(values: tuple[str, ...]) -> str:
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + f" or {values[-1]}"
