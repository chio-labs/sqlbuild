"""Deterministic fingerprinting and persistent canonical scope-index caching."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import cast

from sqlbuild.compiler.discovery.constants import (
    CANONICAL_AUTHORED_ROOTS,
    LOCAL_CONFIG_FILENAME,
    PROJECT_CONFIG_FILENAME,
)
from sqlbuild.compiler.scopes._helpers.lookup import build_lookup
from sqlbuild.compiler.scopes._helpers.paths import normalize_path
from sqlbuild.compiler.scopes.constants import (
    GLOBAL_DECLARATION_DIRECTORIES,
    SCOPE_CACHE_DIRECTORY,
    SCOPE_CACHE_FILENAME,
    SCOPE_CACHE_MAX_BYTES,
    SCOPE_CACHE_SCHEMA_VERSION,
    SCOPE_FINGERPRINT_ALGORITHM_VERSION,
    SCOPE_LOCAL_CONFIG_KEYS,
    SCOPE_MACRO_SUFFIX,
    SCOPE_PROJECT_CONFIG_KEYS,
    SCOPE_RELATIONSHIP_ROOTS,
    SCOPE_SOURCE_SUFFIXES,
)
from sqlbuild.compiler.scopes.exceptions import ScopeCacheDecodeError
from sqlbuild.compiler.scopes.models import (
    ConstantMetadata,
    DeclarationIdentity,
    DeclarationRecord,
    EnumMemberMetadata,
    EnumMetadata,
    GrantRecord,
    InaccessibleRecord,
    MacroMetadata,
    OwnershipRoot,
    ResourceIdentity,
    ResourceRecord,
    ScopeCompleteness,
    ScopeDiagnostic,
    ScopeIndex,
    UsageRecord,
    VisibilityRecord,
)
from sqlbuild.compiler.scopes.types import (
    DeclarationKind,
    DiagnosticSeverity,
    GrantKind,
    InaccessibleReason,
    JsonObject,
    OwnershipRootKind,
    ResourceKind,
    ScopeCacheIdentityType,
    ScopeDiagnosticCode,
    ScopeKind,
    UsageKind,
    VisibilityReason,
)

_CONFIG_FILES: tuple[str, ...] = (
    PROJECT_CONFIG_FILENAME,
    LOCAL_CONFIG_FILENAME,
    ".sqlbuildignore",
    ".gitignore",
)


def encode_scope_index(*, index: ScopeIndex) -> bytes:
    """Encode a canonical ScopeIndex payload as deterministic ASCII JSON."""

    canonical: ScopeIndex = build_lookup(index=index).index
    return json.dumps(
        _index_payload(canonical),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def decode_scope_index(*, payload: object) -> ScopeIndex:
    """Decode a validated cache payload into immutable scope records."""

    value: JsonObject = _object(payload)
    return ScopeIndex(
        ownership_roots=tuple(_root(item) for item in _list(value=value, key="ownership_roots")),
        resources=tuple(_resource(item) for item in _list(value=value, key="resources")),
        declarations=tuple(_declaration(item) for item in _list(value=value, key="declarations")),
        usages=tuple(_usage(item) for item in _list(value=value, key="usages")),
        grants=tuple(_grant(item) for item in _list(value=value, key="grants")),
        visibility=tuple(_visibility(item) for item in _list(value=value, key="visibility")),
        inaccessible=tuple(_inaccessible(item) for item in _list(value=value, key="inaccessible")),
        diagnostics=tuple(_diagnostic(item) for item in _list(value=value, key="diagnostics")),
        completeness=_completeness(value.get("completeness")),
    )


def _index_payload(index: ScopeIndex) -> JsonObject:
    return {
        "ownership_roots": [_root_payload(item) for item in index.ownership_roots],
        "resources": [_resource_payload(item) for item in index.resources],
        "declarations": [_declaration_payload(item) for item in index.declarations],
        "usages": [_usage_payload(item) for item in index.usages],
        "grants": [_grant_payload(item) for item in index.grants],
        "visibility": [_visibility_payload(item) for item in index.visibility],
        "inaccessible": [_inaccessible_payload(item) for item in index.inaccessible],
        "diagnostics": [_diagnostic_payload(item) for item in index.diagnostics],
        "completeness": {
            "discovery": index.completeness.discovery,
            "static_visibility": index.completeness.static_visibility,
            "runtime_usage": index.completeness.runtime_usage,
            "relationships": index.completeness.relationships,
            "placement": index.completeness.placement,
            "promotion_impact": index.completeness.promotion_impact,
        },
    }


def _identity_payload(item: ResourceIdentity | DeclarationIdentity | None) -> object:
    if item is None:
        return None
    if isinstance(item, ResourceIdentity):
        return {
            "type": ScopeCacheIdentityType.RESOURCE.value,
            "kind": item.kind.value,
            "name": item.name,
        }
    return {
        "type": ScopeCacheIdentityType.DECLARATION.value,
        "kind": item.kind.value,
        "name": item.name,
        "owner": _identity_payload(item.owner),
    }


def _identity(payload: object) -> ResourceIdentity | DeclarationIdentity:
    item: JsonObject = _object(payload)
    if item.get("type") == ScopeCacheIdentityType.RESOURCE:
        return ResourceIdentity(
            ResourceKind(_string(value=item, key="kind")),
            _string(value=item, key="name"),
        )
    if item.get("type") != ScopeCacheIdentityType.DECLARATION:
        raise ScopeCacheDecodeError("Invalid cache identity type")
    owner_payload: object = item.get("owner")
    owner: ResourceIdentity | None = None
    if owner_payload is not None:
        decoded: ResourceIdentity | DeclarationIdentity = _identity(owner_payload)
        if not isinstance(decoded, ResourceIdentity):
            raise ScopeCacheDecodeError("Invalid cached declaration owner")
        owner = decoded
    return DeclarationIdentity(
        DeclarationKind(_string(value=item, key="kind")),
        _string(value=item, key="name"),
        owner,
    )


def _root_payload(item: OwnershipRoot) -> JsonObject:
    return {
        "path": normalize_path(path=item.path),
        "kind": item.kind.value,
        "resource_kind": item.resource_kind.value if item.resource_kind is not None else None,
    }


def _root(payload: object) -> OwnershipRoot:
    item: JsonObject = _object(payload)
    resource_kind: object = item.get("resource_kind")
    return OwnershipRoot(
        path=normalize_path(path=_string(value=item, key="path")),
        kind=OwnershipRootKind(_string(value=item, key="kind")),
        resource_kind=ResourceKind(resource_kind) if isinstance(resource_kind, str) else None,
    )


def _resource_payload(item: ResourceRecord) -> JsonObject:
    return {
        "identity": _identity_payload(item.identity),
        "path": normalize_path(path=item.path),
        "ownership_root": _root_payload(item.ownership_root),
    }


def _resource(payload: object) -> ResourceRecord:
    item: JsonObject = _object(payload)
    identity: ResourceIdentity | DeclarationIdentity = _identity(item.get("identity"))
    if not isinstance(identity, ResourceIdentity):
        raise ScopeCacheDecodeError("Invalid cached resource identity")
    return ResourceRecord(
        identity,
        normalize_path(path=_string(value=item, key="path")),
        _root(item.get("ownership_root")),
    )


def _declaration_payload(item: DeclarationRecord) -> JsonObject:
    macro: object = None
    if item.macro is not None:
        macro = {
            "parameters": list(item.macro.parameters),
            "dependencies": [_identity_payload(value) for value in item.macro.dependencies],
            "source_digest": item.macro.source_digest,
        }
    enum: object = None
    if item.enum is not None:
        enum = {
            "members": [{"name": value.name, "value": value.value} for value in item.enum.members],
            "scalar_type": item.enum.scalar_type,
        }
    constant: object = None
    if item.constant is not None:
        constant = {
            "logical_type": item.constant.logical_type,
            "collection_kind": item.constant.collection_kind,
            "item_count": item.constant.item_count,
            "nullable": item.constant.nullable,
            "render_as": item.constant.render_as,
        }
    return {
        "identity": _identity_payload(item.identity),
        "path": normalize_path(path=item.path),
        "line": item.line,
        "column": item.column,
        "scope": item.scope.value,
        "ownership_root": _root_payload(item.ownership_root),
        "owning_path": (
            normalize_path(path=item.owning_path) if item.owning_path is not None else None
        ),
        "macro": macro,
        "enum": enum,
        "constant": constant,
    }


def _declaration(payload: object) -> DeclarationRecord:
    item: JsonObject = _object(payload)
    identity: ResourceIdentity | DeclarationIdentity = _identity(item.get("identity"))
    if not isinstance(identity, DeclarationIdentity):
        raise ScopeCacheDecodeError("Invalid cached declaration identity")
    macro_payload: object = item.get("macro")
    macro: MacroMetadata | None = None
    if macro_payload is not None:
        value: JsonObject = _object(macro_payload)
        dependencies: list[DeclarationIdentity] = []
        for raw in _list(value=value, key="dependencies"):
            decoded: ResourceIdentity | DeclarationIdentity = _identity(raw)
            if not isinstance(decoded, DeclarationIdentity):
                raise ScopeCacheDecodeError("Invalid cached macro dependency")
            dependencies.append(decoded)
        macro = MacroMetadata(
            parameters=tuple(_strings(value=value, key="parameters")),
            dependencies=tuple(dependencies),
            source_digest=_string(value=value, key="source_digest"),
        )
    enum_payload: object = item.get("enum")
    enum: EnumMetadata | None = None
    if enum_payload is not None:
        value = _object(enum_payload)
        members: list[EnumMemberMetadata] = []
        for raw in _list(value=value, key="members"):
            member: JsonObject = _object(raw)
            scalar: object = member.get("value")
            if not isinstance(scalar, str | int) or isinstance(scalar, bool):
                raise ScopeCacheDecodeError("Invalid cached enum value")
            members.append(EnumMemberMetadata(_string(value=member, key="name"), scalar))
        enum = EnumMetadata(tuple(members), _string(value=value, key="scalar_type"))
    constant_payload: object = item.get("constant")
    constant: ConstantMetadata | None = None
    if constant_payload is not None:
        value = _object(constant_payload)
        constant = ConstantMetadata(
            logical_type=_string(value=value, key="logical_type"),
            collection_kind=_optional_string(value.get("collection_kind")),
            item_count=_optional_int(value.get("item_count")),
            nullable=_bool(value=value, key="nullable"),
            render_as=_optional_string(value.get("render_as")),
        )
    return DeclarationRecord(
        identity=identity,
        path=normalize_path(path=_string(value=item, key="path")),
        line=_int(value=item, key="line"),
        column=_int(value=item, key="column"),
        scope=ScopeKind(_string(value=item, key="scope")),
        ownership_root=_root(item.get("ownership_root")),
        owning_path=_optional_path(item.get("owning_path")),
        macro=macro,
        enum=enum,
        constant=constant,
    )


def _usage_payload(item: UsageRecord) -> JsonObject:
    return {
        "consumer": _identity_payload(item.consumer),
        "declaration": _identity_payload(item.declaration),
        "kind": item.kind.value,
        "through": _identity_payload(item.through),
        "enum_member": item.enum_member,
    }


def _usage(payload: object) -> UsageRecord:
    item: JsonObject = _object(payload)
    consumer: ResourceIdentity | DeclarationIdentity = _identity(item.get("consumer"))
    declaration: ResourceIdentity | DeclarationIdentity = _identity(item.get("declaration"))
    through_payload: object = item.get("through")
    through: ResourceIdentity | None = None
    if through_payload is not None:
        decoded: ResourceIdentity | DeclarationIdentity = _identity(through_payload)
        if not isinstance(decoded, ResourceIdentity):
            raise ScopeCacheDecodeError("Invalid cached usage through identity")
        through = decoded
    if not isinstance(declaration, DeclarationIdentity):
        raise ScopeCacheDecodeError("Invalid cached usage declaration")
    return UsageRecord(
        consumer,
        declaration,
        UsageKind(_string(value=item, key="kind")),
        through,
        _optional_string(item.get("enum_member")),
    )


def _grant_payload(item: GrantRecord) -> JsonObject:
    return {
        "resource": _identity_payload(item.resource),
        "declaration": _identity_payload(item.declaration),
        "through": _identity_payload(item.through),
        "kind": item.kind.value,
    }


def _grant(payload: object) -> GrantRecord:
    item: JsonObject = _object(payload)
    resource: ResourceIdentity | DeclarationIdentity
    declaration: ResourceIdentity | DeclarationIdentity
    through: ResourceIdentity | DeclarationIdentity
    resource, declaration, through = (
        _identity(item.get("resource")),
        _identity(item.get("declaration")),
        _identity(item.get("through")),
    )
    if not isinstance(resource, ResourceIdentity) or not isinstance(through, ResourceIdentity):
        raise ScopeCacheDecodeError("Invalid cached grant resource")
    if not isinstance(declaration, DeclarationIdentity):
        raise ScopeCacheDecodeError("Invalid cached grant declaration")
    return GrantRecord(resource, declaration, through, GrantKind(_string(value=item, key="kind")))


def _visibility_payload(item: VisibilityRecord) -> JsonObject:
    return {
        "resource": _identity_payload(item.resource),
        "declaration": _identity_payload(item.declaration),
        "reason": item.reason.value,
        "through": _identity_payload(item.through),
    }


def _visibility(payload: object) -> VisibilityRecord:
    item: JsonObject = _object(payload)
    resource: ResourceIdentity | DeclarationIdentity = _identity(item.get("resource"))
    declaration: ResourceIdentity | DeclarationIdentity = _identity(item.get("declaration"))
    through_payload: object = item.get("through")
    through: ResourceIdentity | DeclarationIdentity | None = (
        _identity(through_payload) if through_payload is not None else None
    )
    if not isinstance(resource, ResourceIdentity) or not isinstance(
        declaration, DeclarationIdentity
    ):
        raise ScopeCacheDecodeError("Invalid cached visibility identity")
    if through is not None and not isinstance(through, ResourceIdentity):
        raise ScopeCacheDecodeError("Invalid cached visibility through identity")
    return VisibilityRecord(
        resource,
        declaration,
        VisibilityReason(_string(value=item, key="reason")),
        through,
    )


def _inaccessible_payload(item: InaccessibleRecord) -> JsonObject:
    return {
        "resource": _identity_payload(item.resource),
        "declaration": _identity_payload(item.declaration),
        "reason": item.reason.value,
    }


def _inaccessible(payload: object) -> InaccessibleRecord:
    item: JsonObject = _object(payload)
    resource: ResourceIdentity | DeclarationIdentity = _identity(item.get("resource"))
    declaration: ResourceIdentity | DeclarationIdentity = _identity(item.get("declaration"))
    if not isinstance(resource, ResourceIdentity) or not isinstance(
        declaration, DeclarationIdentity
    ):
        raise ScopeCacheDecodeError("Invalid cached inaccessible identity")
    return InaccessibleRecord(
        resource, declaration, InaccessibleReason(_string(value=item, key="reason"))
    )


def _diagnostic_payload(item: ScopeDiagnostic) -> JsonObject:
    return {
        "code": item.code.value,
        "message": item.message,
        "severity": item.severity.value,
        "path": normalize_path(path=item.path) if item.path is not None else None,
        "line": item.line,
        "column": item.column,
        "declaration": _identity_payload(item.declaration),
        "resource": _identity_payload(item.resource),
    }


def _diagnostic(payload: object) -> ScopeDiagnostic:
    item: JsonObject = _object(payload)
    declaration_payload, resource_payload = item.get("declaration"), item.get("resource")
    declaration: ResourceIdentity | DeclarationIdentity | None = (
        _identity(declaration_payload) if declaration_payload is not None else None
    )
    resource: ResourceIdentity | DeclarationIdentity | None = (
        _identity(resource_payload) if resource_payload is not None else None
    )
    if declaration is not None and not isinstance(declaration, DeclarationIdentity):
        raise ScopeCacheDecodeError("Invalid cached diagnostic declaration")
    if resource is not None and not isinstance(resource, ResourceIdentity):
        raise ScopeCacheDecodeError("Invalid cached diagnostic resource")
    return ScopeDiagnostic(
        ScopeDiagnosticCode(_string(value=item, key="code")),
        _string(value=item, key="message"),
        DiagnosticSeverity(_string(value=item, key="severity")),
        _optional_path(item.get("path")),
        _optional_int(item.get("line")),
        _optional_int(item.get("column")),
        declaration,
        resource,
    )


def _completeness(payload: object) -> ScopeCompleteness:
    item: JsonObject = _object(payload)
    return ScopeCompleteness(
        **{
            key: _bool(value=item, key=key)
            for key in (
                "discovery",
                "static_visibility",
                "runtime_usage",
                "relationships",
                "placement",
                "promotion_impact",
            )
        }
    )


def _object(value: object) -> JsonObject:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ScopeCacheDecodeError("Expected a JSON object in scope cache")
    return cast(JsonObject, value)


def _list(*, value: JsonObject, key: str) -> list[object]:
    item: object = value.get(key)
    if not isinstance(item, list):
        raise ScopeCacheDecodeError(f"Expected a list for cached field '{key}'")
    return cast(list[object], item)


def _string(*, value: JsonObject, key: str) -> str:
    item: object = value.get(key)
    if not isinstance(item, str):
        raise ScopeCacheDecodeError(f"Expected a string for cached field '{key}'")
    return item


def _strings(*, value: JsonObject, key: str) -> list[str]:
    items: list[object] = _list(value=value, key=key)
    if not all(isinstance(item, str) for item in items):
        raise ScopeCacheDecodeError(f"Expected strings for cached field '{key}'")
    return cast(list[str], items)


def _int(*, value: JsonObject, key: str) -> int:
    item: object = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise ScopeCacheDecodeError(f"Expected an integer for cached field '{key}'")
    return item


def _bool(*, value: JsonObject, key: str) -> bool:
    item: object = value.get(key)
    if not isinstance(item, bool):
        raise ScopeCacheDecodeError(f"Expected a boolean for cached field '{key}'")
    return item


def _optional_string(value: object) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ScopeCacheDecodeError("Expected an optional string in scope cache")
    return value


def _optional_int(value: object) -> int | None:
    if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
        raise ScopeCacheDecodeError("Expected an optional integer in scope cache")
    return value


def _optional_path(value: object) -> str | None:
    path: str | None = _optional_string(value)
    return normalize_path(path=path) if path is not None else None


def scope_index_fingerprint(*, project_dir: Path) -> str:
    """Hash canonical scope-relevant authored inputs without absolute paths or secrets."""

    records: list[dict[str, object]] = []
    for name in _CONFIG_FILES:
        path: Path = project_dir / name
        if not path.is_file():
            continue
        raw: bytes = path.read_bytes()
        content: bytes = _scope_config_bytes(name=name, raw=raw)
        records.append(_fingerprint_record(path=name, role="config", content=content))
    roots: tuple[str, ...] = tuple(
        sorted(
            {
                *(Path(*parts).as_posix() for parts in CANONICAL_AUTHORED_ROOTS),
                *GLOBAL_DECLARATION_DIRECTORIES,
                "schemas",
            }
        )
    )
    seen: set[str] = set()
    for root in roots:
        directory: Path = project_dir / root
        if not directory.is_dir():
            continue
        for path in sorted(item for item in directory.rglob("*") if item.is_file()):
            if path.suffix.lower() not in SCOPE_SOURCE_SUFFIXES:
                continue
            relative: str = path.relative_to(project_dir).as_posix()
            if relative in seen:
                continue
            seen.add(relative)
            records.append(
                _fingerprint_record(
                    path=relative,
                    role=_source_role(path=Path(relative)),
                    content=path.read_bytes(),
                )
            )
    payload: dict[str, object] = {
        "algorithm_version": SCOPE_FINGERPRINT_ALGORITHM_VERSION,
        "cache_schema_version": SCOPE_CACHE_SCHEMA_VERSION,
        "ownership_roots": list(roots),
        "sources": sorted(records, key=lambda item: (str(item["path"]), str(item["role"]))),
        "sqlbuild_version": _sqlbuild_version(),
    }
    encoded: bytes = _canonical_json(payload)
    return hashlib.sha256(encoded).hexdigest()


def read_cached_scope_index(*, project_dir: Path, fingerprint: str) -> ScopeIndex | None:
    """Read a verified index; every storage or validation fault is a cache miss."""

    path: Path = project_dir / SCOPE_CACHE_DIRECTORY / SCOPE_CACHE_FILENAME
    try:
        if path.stat().st_size > SCOPE_CACHE_MAX_BYTES:
            return None
        raw: bytes = path.read_bytes()
        envelope: object = json.loads(raw.decode("utf-8"))
        if not isinstance(envelope, dict):
            return None
        if envelope.get("schema_version") != SCOPE_CACHE_SCHEMA_VERSION:
            return None
        if envelope.get("input_fingerprint") != fingerprint:
            return None
        payload: object = envelope.get("payload")
        payload_bytes: bytes = _canonical_json(payload)
        if envelope.get("payload_sha256") != hashlib.sha256(payload_bytes).hexdigest():
            return None
        return decode_scope_index(payload=payload)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None


def write_cached_scope_index(*, project_dir: Path, fingerprint: str, index: ScopeIndex) -> None:
    """Atomically write one complete canonical scope index, ignoring I/O faults."""

    if not index.completeness.complete:
        return
    try:
        payload: object = json.loads(encode_scope_index(index=index).decode("ascii"))
        payload_bytes: bytes = _canonical_json(payload)
        envelope: bytes = _canonical_json(
            {
                "input_fingerprint": fingerprint,
                "payload": payload,
                "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
                "schema_version": SCOPE_CACHE_SCHEMA_VERSION,
            }
        )
        directory: Path = project_dir / SCOPE_CACHE_DIRECTORY
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".scope-index-", dir=directory)
        temporary_path: Path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(envelope)
                stream.flush()
                os.fsync(stream.fileno())
            temporary_path.replace(directory / SCOPE_CACHE_FILENAME)
        finally:
            temporary_path.unlink(missing_ok=True)
    except (OSError, TypeError, ValueError):
        return


def _fingerprint_record(*, path: str, role: str, content: bytes) -> dict[str, object]:
    return {
        "path": path.replace("\\", "/"),
        "role": role,
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _source_role(*, path: Path) -> str:
    parts: tuple[str, ...] = path.parts
    if any(part in GLOBAL_DECLARATION_DIRECTORIES for part in parts):
        return "declaration"
    if path.suffix == SCOPE_MACRO_SUFFIX:
        return "macro"
    if parts[:2] in SCOPE_RELATIONSHIP_ROOTS:
        return "relationship"
    return "resource"


def _scope_config_bytes(*, name: str, raw: bytes) -> bytes:
    if not name.endswith(".toml"):
        return raw
    try:
        payload: object = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError):
        return raw
    if not isinstance(payload, dict):
        return raw
    relevant: dict[str, object]
    if name == LOCAL_CONFIG_FILENAME:
        relevant = {key: value for key, value in payload.items() if key in SCOPE_LOCAL_CONFIG_KEYS}
    else:
        relevant = {
            key: value for key, value in payload.items() if key in SCOPE_PROJECT_CONFIG_KEYS
        }
    return _canonical_json(relevant)


def _sqlbuild_version() -> str:
    try:
        return version("sqlbuild")
    except PackageNotFoundError:
        return "0+unknown"


def _canonical_json(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "ascii"
    )
