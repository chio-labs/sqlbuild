"""Cache identity for one model's attachment result."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.compile._helpers.render.volatile_reads import environment_read_label
from sqlbuild.compiler.compile.models import (
    DeclarationScopeResolver,
    ModelAttachmentEnvironment,
    ModelInputBuildContext,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredSqlModelFile
from sqlbuild.compiler.fact_cache.classes.fact_cache_store import FactCacheStore
from sqlbuild.compiler.fact_cache.main.code_identity import compiled_code_identity
from sqlbuild.compiler.scopes.models import DeclarationRecord, ResourceIdentity, ResourceRecord
from sqlbuild.compiler.scopes.types import DeclarationKind, ResourceKind

_TARGET_ENVIRONMENT_REFERENCE: re.Pattern[str] = re.compile(r"\bENV:\s*([A-Za-z0-9_]+)")
_PROCESS_LOCAL_REPR_MARKER: str = " at 0x"
_PROJECT_ADAPTERS_DIRECTORY: str = "adapters"
_ENVIRONMENT_DIGEST_BYTES: int = 32
_ATTACHMENT_DECLARATION_KINDS: frozenset[DeclarationKind] = frozenset(
    {
        DeclarationKind.MACRO,
        DeclarationKind.ENUM,
        DeclarationKind.CONSTANT,
        DeclarationKind.SCHEMA,
        DeclarationKind.SQL_HOOK,
        DeclarationKind.PYTHON_HOOK,
    }
)


def model_attachment_environment(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    context: ModelInputBuildContext,
    no_sql_validation: bool,
    defer_model_sql_validation: bool,
) -> ModelAttachmentEnvironment | None:
    """Return the project-wide key part, or None when an input has no stable identity."""

    target_text: str = repr(
        None if context.target_config is None else replace(context.target_config, connection={})
    )
    target_environment_names: tuple[str, ...] = tuple(
        sorted(set(_TARGET_ENVIRONMENT_REFERENCE.findall(target_text)))
    )
    renderer_type: type = type(context.value_renderer)
    material: str = "\0".join(
        (
            compiled_code_identity(),
            str(discovered_inputs.project_dir.resolve() if discovered_inputs.project_dir else ""),
            context.macro_context.adapter_name,
            f"{renderer_type.__module__}.{renderer_type.__qualname__}",
            str(context.collection_rendering),
            context.sql_lexical_syntax.cache_key,
            _project_adapter_sources(discovered_inputs),
            repr(context.effective_target_name),
            target_text,
            repr(tuple((name, os.environ.get(name)) for name in target_environment_names)),
            repr(context.effective_vars),
            repr(context.effective_settings),
            repr(
                (
                    context.macro_context.sql_analysis_enabled,
                    context.macro_context.target_name,
                    discovered_inputs.project_config.references.enforce_explicit,
                    no_sql_validation,
                    defer_model_sql_validation,
                )
            ),
            repr(discovered_inputs.project_config.defaults),
            repr(discovered_inputs.project_config.materialization_defaults),
            repr(sorted(item.name for item in discovered_inputs.materialization_files)),
            repr(sorted(item.name for item in discovered_inputs.providers)),
            _declaration_surface(
                discovered_inputs=discovered_inputs, resolver=context.declaration_resolver
            ),
        )
    )
    if _PROCESS_LOCAL_REPR_MARKER in material:
        return None
    return ModelAttachmentEnvironment(
        digest=hashlib.blake2b(
            material.encode("utf-8", "surrogatepass"), digest_size=_ENVIRONMENT_DIGEST_BYTES
        ).hexdigest(),
        keyed_reads=frozenset(environment_read_label(name) for name in target_environment_names),
    )


def model_attachment_key(
    *,
    store: FactCacheStore,
    environment: ModelAttachmentEnvironment,
    model_file: DiscoveredSqlModelFile,
    path_default: tuple[str | None, object],
    resolver: DeclarationScopeResolver | None,
) -> str:
    """Return the exact identity of one model's attachment inputs."""

    relative_path: str = model_file.relative_path.as_posix()
    return store.key(
        environment.digest,
        relative_path,
        str(model_file.file_path),
        model_file.contents,
        repr(model_file.extract_implicit_alias_columns),
        repr(path_default),
        "" if resolver is None else _resource_scope(resolver=resolver, model_file=model_file),
    )


def _resource_scope(
    *, resolver: DeclarationScopeResolver, model_file: DiscoveredSqlModelFile
) -> str:
    records: tuple[ResourceRecord, ...] = resolver.lookup.resources_by_path.get(
        model_file.relative_path.as_posix(), ()
    )
    identities: tuple[ResourceIdentity, ...] = (
        ResourceIdentity(ResourceKind.MODEL, model_file.file_path.stem),
        *(record.identity for record in records),
    )
    return repr(
        (
            records,
            tuple(
                resolver.lookup.grants_by_resource.get(identity, ())
                for identity in dict.fromkeys(identities)
            ),
        )
    )


def _declaration_surface(
    *, discovered_inputs: DiscoveredProjectInputs, resolver: DeclarationScopeResolver | None
) -> str:
    """Return every shared macro and declaration source; editing one re-attaches every model."""

    parts: list[str] = [
        repr(
            (
                type(item).__name__,
                item.relative_path.as_posix(),
                item.contents,
                item.scope_kind,
                item.ownership_root,
                item.owning_path,
                item.declaration_root,
            )
        )
        for item in (
            *discovered_inputs.macro_files,
            *discovered_inputs.enum_files,
            *discovered_inputs.constant_files,
            *discovered_inputs.model_schema_files,
            *discovered_inputs.sql_hook_files,
        )
    ]
    parts.extend(
        repr(
            (
                hook.name,
                hook.relative_path.as_posix(),
                hook.description,
                hook.reads,
                hook.provider_usages,
                hook.scope_kind,
                hook.ownership_root,
                hook.owning_path,
                hook.declaration_root,
                _source_text(hook.file_path),
            )
        )
        for hook in discovered_inputs.hook_functions
    )
    parts.extend(
        repr(
            (
                factory.name,
                factory.relative_path.as_posix(),
                factory.line,
                factory.cases,
                _source_text(factory.file_path),
            )
        )
        for factory in discovered_inputs.audit_factories
    )
    if resolver is not None:
        parts.extend(
            repr(record)
            for record in resolver.lookup.index.declarations
            if _is_shared_attachment_declaration(record)
        )
    return "\0".join(parts)


def _is_shared_attachment_declaration(record: DeclarationRecord) -> bool:
    owner: ResourceIdentity | None = record.identity.owner
    return record.identity.kind in _ATTACHMENT_DECLARATION_KINDS and (
        owner is None or owner.kind is not ResourceKind.MODEL
    )


def _project_adapter_sources(discovered_inputs: DiscoveredProjectInputs) -> str:
    project_dir: Path | None = discovered_inputs.project_dir
    adapter_paths: tuple[Path, ...] = (
        ()
        if project_dir is None
        else tuple(sorted((project_dir / _PROJECT_ADAPTERS_DIRECTORY).rglob("*.py")))
    )
    return repr(
        (
            _source_text(
                None
                if discovered_inputs.adapter_file is None
                else discovered_inputs.adapter_file.file_path
            ),
            tuple((path.as_posix(), _source_text(path)) for path in adapter_paths),
        )
    )


def _source_text(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="surrogateescape")
    except OSError:
        return ""
