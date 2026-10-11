"""Seeds paired natively with their declarations and held by the compile's native project."""

import sqlbuild._native as _native
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.types import SeedInput
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredSchemaFile
from sqlbuild.spec.contracts.models import SchemaSeedEntry


def attach_seeds(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    native_project: _native.NativeCompiledProject,
) -> tuple[SeedInput, ...]:
    """Pair every declared seed with its CSV file; raise for a declaration without one."""

    declarations: list[tuple[SchemaSeedEntry, DiscoveredSchemaFile]] = []
    for schema_file in discovered_inputs.schema_files:
        declarations.extend((seed_entry, schema_file) for seed_entry in schema_file.seed_entries)
    return tuple(
        native_project.attach_seeds(
            declarations, list(discovered_inputs.seed_files), CompileInputError
        )
    )
