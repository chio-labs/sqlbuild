"""Capture fragments for discovery coverage tests."""

from __future__ import annotations

import dataclasses
from itertools import filterfalse
from typing import cast

from sqlbuild.compiler.compile.models import CompileProjectInputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.frontier.constants import STAGE_CAPTURE_OMITTED_ATTRIBUTES

_VALUE_KIND: str = "sqlbuild.sql_values.types:SqlValueKind"


def constant_declaration(*, kind: str, value: object) -> dict[str, object]:
    """Return one captured constant declaration of a logical kind."""

    return {
        "value": {"logical_type": {"kind": {"__enum__": f"{_VALUE_KIND}.{kind}"}}, "value": value}
    }


def empty_inputs_capture(**overrides: object) -> dict[str, object]:
    """Return a capture with every captured `DiscoveredProjectInputs` field, then overrides."""

    type_name: str = "sqlbuild.compiler.discovery.models:DiscoveredProjectInputs"
    names: list[str] = [field.name for field in dataclasses.fields(DiscoveredProjectInputs)]
    return {
        "__type__": type_name,
        **dict.fromkeys(
            filterfalse(STAGE_CAPTURE_OMITTED_ATTRIBUTES[type_name].__contains__, names), []
        ),
        **overrides,
    }


_DECLARATION_KIND: str = "sqlbuild.compiler.scopes.types:DeclarationKind"
_RESOURCE_KIND: str = "sqlbuild.compiler.scopes.types:ResourceKind"
_AUDIT_TARGET: str = "sqlbuild.compiler.compile.types:AttachedAuditTargetKind"
_REFERENCE_KIND: str = "sqlbuild.compiler.references.types:SqlReferenceKind"


def empty_render_capture(**overrides: object) -> dict[str, object]:
    """Return a capture with every `CompileProjectInputs` field, in order, then overrides."""

    return {
        "__type__": "sqlbuild.compiler.compile.models:CompileProjectInputs",
        **{field.name: [] for field in dataclasses.fields(CompileProjectInputs)},
        **overrides,
    }


def usage(*, kind: str, name: str, enum_member: str | None = None) -> dict[str, object]:
    """Return one captured direct usage of a project declaration."""

    return {
        "declaration": {
            "kind": {"__enum__": f"{_DECLARATION_KIND}.{kind}"},
            "name": name,
            "owner": None,
        },
        "through": None,
        "enum_member": enum_member,
    }


def private_usage(*, kind: str, name: str, owner: str) -> dict[str, object]:
    """Return one captured usage of a declaration private to the model `owner`."""

    direct: dict[str, object] = usage(kind=kind, name=name)
    return {
        **direct,
        "declaration": {**_as_object(direct["declaration"]), "owner": _model(owner)},
    }


def granted_usage(*, kind: str, name: str, through: str) -> dict[str, object]:
    """Return one captured usage granted through the expected model `through`."""

    return {**usage(kind=kind, name=name), "through": _model(through)}


def _model(name: str) -> dict[str, object]:
    return {"kind": {"__enum__": f"{_RESOURCE_KIND}.MODEL"}, "name": name}


def _as_object(value: object) -> dict[str, object]:
    return cast(dict[str, object], value)


def reference(*, kind: str, name: str) -> dict[str, object]:
    """Return one captured SQL reference."""

    return {"ref_kind": {"__enum__": f"{_REFERENCE_KIND}.{kind}"}, "ref_name": name}


def audit_input(*, definition: str, template: str, rendered: str) -> dict[str, object]:
    """Return one captured generic audit attached to column `amount` of model `orders`."""

    return {
        "audit_file": {"relative_path": {"__path__": f"audits/generic/{definition}.sql"}},
        "audit_block": {"sql_body": template},
        "sql_body": rendered,
        "attached_target_kind": {"__enum__": f"{_AUDIT_TARGET}.MODEL"},
        "attached_target_name": "orders",
        "attached_column_name": "amount",
    }
