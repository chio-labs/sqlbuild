"""Canonical authored resource identity validation."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.resource_names.main._validate_resource_identity import (
    validate_resource_identity,
)
from sqlbuild.compiler.scopes.types import ScopeKind

_GENERIC_AUDIT_PATH_PREFIX: tuple[str, str] = ("audits", "generic")


@dataclass(frozen=True)
class _IdentityCandidate:
    name: str
    kind: str
    path: Path
    private_identity: bool = False


def validate_discovered_resource_identities(
    discovered_inputs: DiscoveredProjectInputs,
) -> None:
    """Reject non-canonical identities before graph assembly or persistence."""

    for candidate in _identity_candidates(discovered_inputs):
        validate_resource_identity(
            name=candidate.name,
            kind=candidate.kind,
            path=candidate.path,
            private_identity=candidate.private_identity,
        )


def _identity_candidates(
    discovered_inputs: DiscoveredProjectInputs,
) -> Iterator[_IdentityCandidate]:
    for model_file in discovered_inputs.model_files:
        yield _IdentityCandidate(model_file.file_path.stem, "model", model_file.relative_path)
        for declaration in (*model_file.enum_declarations, *model_file.constant_declarations):
            yield _IdentityCandidate(
                declaration.name,
                "model-local declaration",
                declaration.relative_path,
                private_identity=True,
            )
    for function_file in (
        *discovered_inputs.sql_function_files,
        *discovered_inputs.python_function_files,
    ):
        yield _IdentityCandidate(
            function_file.file_path.stem, "function", function_file.relative_path
        )
    for hook_file in discovered_inputs.sql_hook_files:
        yield _IdentityCandidate(hook_file.name, "SQL hook", hook_file.relative_path)
    for seed_file in discovered_inputs.seed_files:
        yield _IdentityCandidate(seed_file.file_path.stem, "seed", seed_file.relative_path)
    for schema_file in discovered_inputs.schema_files:
        for model_entry in schema_file.model_entries:
            yield _IdentityCandidate(model_entry.name, "schema model", schema_file.relative_path)
        for seed_entry in schema_file.seed_entries:
            yield _IdentityCandidate(seed_entry.name, "schema seed", schema_file.relative_path)
    for source_file in discovered_inputs.source_files:
        for source_entry in source_file.source_entries:
            yield _IdentityCandidate(source_entry.name, "source", source_file.relative_path)
    for test_file in discovered_inputs.test_files:
        for block in test_file.blocks:
            yield _IdentityCandidate(
                block.name or test_file.relative_path.stem,
                "SQL test",
                test_file.relative_path,
            )
            for case in block.cases:
                yield _IdentityCandidate(case.name, "SQL test case", test_file.relative_path)
    for scenario_file in discovered_inputs.scenario_files:
        yield _IdentityCandidate(scenario_file.name, "scenario", scenario_file.relative_path)
    for audit_file in discovered_inputs.audit_files:
        for block in audit_file.blocks:
            is_generic: bool = audit_file.relative_path.parts[:2] == _GENERIC_AUDIT_PATH_PREFIX
            yield _IdentityCandidate(
                (
                    audit_file.relative_path.stem
                    if is_generic
                    else block.name or audit_file.relative_path.stem
                ),
                "audit",
                audit_file.relative_path,
            )
            if is_generic and block.name is not None:
                yield _IdentityCandidate(
                    block.name,
                    "generic audit instance",
                    audit_file.relative_path,
                )
    for declaration_file in (
        *discovered_inputs.enum_files,
        *discovered_inputs.constant_files,
    ):
        for declaration in declaration_file.declarations:
            yield _IdentityCandidate(
                declaration.name,
                "declaration",
                declaration.relative_path,
                private_identity=declaration_file.scope_kind is ScopeKind.PRIVATE,
            )
    for schema_file in discovered_inputs.model_schema_files:
        for declaration in schema_file.declarations:
            yield _IdentityCandidate(declaration.name, "model schema", declaration.relative_path)
    for named_resources, kind in (
        (discovered_inputs.materialization_files, "materialization"),
        (discovered_inputs.loader_functions, "loader"),
        (discovered_inputs.task_functions, "task"),
        (discovered_inputs.asset_functions, "asset"),
        (discovered_inputs.check_functions, "check"),
        (discovered_inputs.hook_functions, "Python hook"),
        (discovered_inputs.event_exporters, "event exporter"),
        (discovered_inputs.providers, "provider"),
    ):
        for resource in named_resources:
            yield _IdentityCandidate(resource.name, kind, resource.relative_path)
