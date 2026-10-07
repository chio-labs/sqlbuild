"""The builder's walk of discovered inputs as the plain rows the native scope index reads."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from sqlbuild.compiler.compile.models import LoadedMacro
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredAuditFile,
    DiscoveredHookFunction,
    DiscoveredMacroFile,
    DiscoveredModelSchemaFile,
    DiscoveredProjectInputs,
    DiscoveredSqlHookFile,
    EnumDeclaration,
)
from sqlbuild.compiler.scopes._helpers.builder import (
    constant_metadata,
    enum_metadata,
    macro_line,
    macro_metadata,
)
from sqlbuild.compiler.scopes._helpers.paths import normalize_path
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    NativeDeclarationValues,
    ResourceIdentity,
)
from sqlbuild.compiler.scopes.types import (
    DeclarationKind,
    NativeDeclarationRow,
    NativeIdentityRow,
    NativeResourceRow,
    ResourceKind,
    ScopeKind,
)

_KIND_ROOT: str = "kind"
_SEED_ROOT: str = "seed"
_PYTHON_FUNCTION_ROOT: str = "python_function"
_PRIVATE_ROOT: str = "models"
_MACRO_FALLBACK: str = "macros"
_ENUM_FALLBACK: str = "enums"
_CONSTANT_FALLBACK: str = "constants"


class NativeScopeRows:
    """Resource and declaration rows in the Python builder's walk order, without records."""

    def __init__(
        self,
        *,
        discovered_inputs: DiscoveredProjectInputs,
        loaded_macros: Mapping[str, LoadedMacro],
    ) -> None:
        self.resources: list[NativeResourceRow] = []
        self.resource_identities: list[ResourceIdentity] = []
        self.resource_roots: list[str] = []
        self.declarations: list[NativeDeclarationRow] = []
        self.declaration_values: list[NativeDeclarationValues] = []
        self._add_models(discovered_inputs=discovered_inputs)
        self._add_resources(discovered_inputs=discovered_inputs)
        self._add_declaration_files(discovered_inputs=discovered_inputs)
        self._add_named_declarations(discovered_inputs=discovered_inputs)
        self._add_macros(discovered_inputs=discovered_inputs, loaded_macros=loaded_macros)

    def _add_resource(self, *, kind: ResourceKind, name: str, path: Path, root: str) -> None:
        self.resources.append((kind.value, name, str(path), root))
        self.resource_identities.append(ResourceIdentity(kind, name))
        self.resource_roots.append(root)

    def _add_declaration(
        self,
        *,
        values: NativeDeclarationValues,
        path: Path | str,
        ownership_root: Path | str | None,
        root_fallback: Path | str,
        owning_path: Path | str | None,
    ) -> None:
        identity: DeclarationIdentity = values.identity
        self.declarations.append(
            (
                identity.kind.value,
                identity.name,
                _identity_row(identity.owner),
                str(path),
                values.line,
                values.scope.value,
                None if ownership_root is None else str(ownership_root),
                str(root_fallback),
                None if owning_path is None else str(owning_path),
                [
                    (item.kind.value, item.name, _identity_row(item.owner))
                    for item in values.dependencies
                ],
            )
        )
        self.declaration_values.append(values)

    def _add_models(self, *, discovered_inputs: DiscoveredProjectInputs) -> None:
        for model_file in discovered_inputs.model_files:
            model_name: str = _name_or_stem(
                value=model_file.header_values.get("name"), path=model_file.relative_path
            )
            self._add_resource(
                kind=ResourceKind.MODEL,
                name=model_name,
                path=model_file.relative_path,
                root=_KIND_ROOT,
            )
            owner: ResourceIdentity = ResourceIdentity(ResourceKind.MODEL, model_name)
            for enum in model_file.enum_declarations:
                self._add_private(declaration=enum, owner=owner, path=model_file.relative_path)
            for constant in model_file.constant_declarations:
                self._add_private(declaration=constant, owner=owner, path=model_file.relative_path)

    def _add_private(
        self,
        *,
        declaration: EnumDeclaration | ConstantDeclaration,
        owner: ResourceIdentity,
        path: Path,
    ) -> None:
        values: NativeDeclarationValues = (
            NativeDeclarationValues(
                identity=DeclarationIdentity(DeclarationKind.ENUM, declaration.name, owner),
                line=1,
                scope=ScopeKind.PRIVATE,
                enum=enum_metadata(declaration),
            )
            if isinstance(declaration, EnumDeclaration)
            else NativeDeclarationValues(
                identity=DeclarationIdentity(DeclarationKind.CONSTANT, declaration.name, owner),
                line=1,
                scope=ScopeKind.PRIVATE,
                constant=constant_metadata(declaration),
            )
        )
        self._add_declaration(
            values=values,
            path=path,
            ownership_root=_PRIVATE_ROOT,
            root_fallback=_PRIVATE_ROOT,
            owning_path=path.parent,
        )

    def _add_resources(self, *, discovered_inputs: DiscoveredProjectInputs) -> None:
        for test_file in discovered_inputs.test_files:
            for block in test_file.blocks:
                self._add_resource(
                    kind=ResourceKind.TEST,
                    name=block.name or test_file.relative_path.stem,
                    path=test_file.relative_path,
                    root=_KIND_ROOT,
                )
        for scenario_file in discovered_inputs.scenario_files:
            self._add_resource(
                kind=ResourceKind.SCENARIO,
                name=scenario_file.name,
                path=scenario_file.relative_path,
                root=_KIND_ROOT,
            )
        for function_file in discovered_inputs.sql_function_files:
            self._add_resource(
                kind=ResourceKind.FUNCTION,
                name=_name_or_stem(
                    value=function_file.header_values.get("name"),
                    path=function_file.relative_path,
                ),
                path=function_file.relative_path,
                root=_KIND_ROOT,
            )
        for python_function_file in discovered_inputs.python_function_files:
            self._add_resource(
                kind=ResourceKind.FUNCTION,
                name=python_function_file.file_path.stem,
                path=python_function_file.relative_path,
                root=_PYTHON_FUNCTION_ROOT,
            )
        for seed_file in discovered_inputs.seed_files:
            self._add_resource(
                kind=ResourceKind.SEED,
                name=seed_file.file_path.stem,
                path=seed_file.relative_path,
                root=_SEED_ROOT,
            )
        for source_file in discovered_inputs.source_files:
            for source in source_file.source_entries:
                self._add_resource(
                    kind=ResourceKind.SOURCE,
                    name=source.name,
                    path=source_file.relative_path,
                    root=_KIND_ROOT,
                )

    def _add_declaration_files(self, *, discovered_inputs: DiscoveredProjectInputs) -> None:
        for enum_file in discovered_inputs.enum_files:
            for enum in enum_file.declarations:
                self._add_declaration(
                    values=NativeDeclarationValues(
                        identity=DeclarationIdentity(DeclarationKind.ENUM, enum.name),
                        line=1,
                        scope=enum_file.scope_kind,
                        enum=enum_metadata(enum),
                    ),
                    path=enum_file.relative_path,
                    ownership_root=enum_file.ownership_root,
                    root_fallback=_ENUM_FALLBACK,
                    owning_path=enum_file.owning_path,
                )
        for constant_file in discovered_inputs.constant_files:
            for constant in constant_file.declarations:
                self._add_declaration(
                    values=NativeDeclarationValues(
                        identity=DeclarationIdentity(DeclarationKind.CONSTANT, constant.name),
                        line=1,
                        scope=constant_file.scope_kind,
                        constant=constant_metadata(constant),
                    ),
                    path=constant_file.relative_path,
                    ownership_root=constant_file.ownership_root,
                    root_fallback=_CONSTANT_FALLBACK,
                    owning_path=constant_file.owning_path,
                )

    def _add_named_declarations(self, *, discovered_inputs: DiscoveredProjectInputs) -> None:
        for audit_file in discovered_inputs.audit_files:
            if audit_file.declaration_kind is DeclarationKind.AUDIT:
                self._add_named(
                    item=audit_file,
                    kind=DeclarationKind.AUDIT,
                    name=audit_file.relative_path.stem,
                    path=audit_file.relative_path,
                )
                continue
            for block in audit_file.blocks:
                self._add_named(
                    item=audit_file,
                    kind=DeclarationKind.SINGULAR_AUDIT,
                    name=block.name or audit_file.relative_path.stem,
                    path=audit_file.relative_path,
                )
        for schema_file in discovered_inputs.model_schema_files:
            for declaration in schema_file.declarations:
                self._add_named(
                    item=schema_file,
                    kind=DeclarationKind.SCHEMA,
                    name=declaration.name,
                    path=schema_file.relative_path,
                )
        for hook_file in discovered_inputs.sql_hook_files:
            self._add_named(
                item=hook_file,
                kind=DeclarationKind.SQL_HOOK,
                name=hook_file.name,
                path=hook_file.relative_path,
            )
        for hook_function in discovered_inputs.hook_functions:
            self._add_named(
                item=hook_function,
                kind=DeclarationKind.PYTHON_HOOK,
                name=hook_function.name,
                path=hook_function.relative_path,
            )

    def _add_named(
        self,
        *,
        item: DiscoveredAuditFile
        | DiscoveredModelSchemaFile
        | DiscoveredSqlHookFile
        | DiscoveredHookFunction,
        kind: DeclarationKind,
        name: str,
        path: Path,
    ) -> None:
        self._add_declaration(
            values=NativeDeclarationValues(
                identity=DeclarationIdentity(kind, name), line=1, scope=item.scope_kind
            ),
            path=path,
            ownership_root=item.ownership_root,
            root_fallback=item.declaration_root or item.relative_path.parent,
            owning_path=item.owning_path,
        )

    def _add_macros(
        self,
        *,
        discovered_inputs: DiscoveredProjectInputs,
        loaded_macros: Mapping[str, LoadedMacro],
    ) -> None:
        macro_files: dict[str, DiscoveredMacroFile] = {
            normalize_path(path=item.relative_path): item for item in discovered_inputs.macro_files
        }
        for loaded in loaded_macros.values():
            discovered: DiscoveredMacroFile | None = macro_files.get(
                normalize_path(path=loaded.relative_path)
            )
            self._add_declaration(
                values=NativeDeclarationValues(
                    identity=DeclarationIdentity(DeclarationKind.MACRO, loaded.name),
                    line=macro_line(loaded),
                    scope=discovered.scope_kind if discovered is not None else ScopeKind.GLOBAL,
                    macro=macro_metadata(loaded),
                    dependencies=loaded.dependencies,
                ),
                path=loaded.relative_path,
                ownership_root=discovered.ownership_root if discovered is not None else None,
                root_fallback=_MACRO_FALLBACK,
                owning_path=discovered.owning_path if discovered is not None else None,
            )


def _identity_row(identity: ResourceIdentity | None) -> NativeIdentityRow | None:
    return None if identity is None else (identity.kind.value, identity.name)


def _name_or_stem(*, value: object, path: Path) -> str:
    return value if isinstance(value, str) and value else path.stem
