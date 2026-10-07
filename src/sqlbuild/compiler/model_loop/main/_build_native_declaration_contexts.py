"""Hand one scope lookup to the native declaration context classifier."""

from __future__ import annotations

from collections.abc import Mapping

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import (
    DeclarationResolutionContext,
    LoadedMacro,
)
from sqlbuild.compiler.discovery.models import ConstantDeclaration, EnumDeclaration
from sqlbuild.compiler.model_loop.constants import DECLARATION_KIND_CODES, NO_DECLARATION_KIND
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationVisibilityIndex,
    ScopeLookup,
    VisibilityRecord,
)
from sqlbuild.compiler.scopes.types import DeclarationKind, VisibilityReason


def build_native_declaration_contexts(
    *,
    lookup: ScopeLookup,
    declarations: Mapping[DeclarationIdentity, EnumDeclaration | ConstantDeclaration | LoadedMacro],
) -> _native.NativeDeclarationContexts:
    """Hand the lookup's declaration positions and runtime values to the native classifier."""

    index: DeclarationVisibilityIndex = lookup.visibility_index
    identity_keys: dict[DeclarationIdentity, int] = {}
    positions: list[tuple[object, ...]] = []
    for identity in index.identities:
        key: int = identity_keys.setdefault(identity, len(identity_keys))
        value: EnumDeclaration | ConstantDeclaration | LoadedMacro | None = declarations.get(
            identity
        )
        positions.append(
            (
                identity,
                lookup.declarations[identity][0],
                identity.name,
                DECLARATION_KIND_CODES.get(identity.kind, NO_DECLARATION_KIND),
                value,
                _value_kind(value),
                key,
            )
        )
    return _native.NativeDeclarationContexts(
        positions,
        (
            list(index.global_positions),
            {owner: list(items) for owner, items in index.local_positions.items()},
            {owner: list(items) for owner, items in index.inherited_positions.items()},
        ),
        {
            "visibility_record": VisibilityRecord,
            "resolution_context": DeclarationResolutionContext,
            "allocate": object.__new__,
            "reasons": {reason.value: reason for reason in VisibilityReason},
        },
        {
            "identity_keys": identity_keys,
            "private_positions": index.private_positions,
            "grants_by_resource": lookup.grants_by_resource,
        },
    )


def _value_kind(value: EnumDeclaration | ConstantDeclaration | LoadedMacro | None) -> int:
    if isinstance(value, EnumDeclaration):
        return DECLARATION_KIND_CODES[DeclarationKind.ENUM]
    if isinstance(value, ConstantDeclaration):
        return DECLARATION_KIND_CODES[DeclarationKind.CONSTANT]
    if isinstance(value, LoadedMacro):
        return DECLARATION_KIND_CODES[DeclarationKind.MACRO]
    return NO_DECLARATION_KIND
