"""Seeds, functions and sources attached natively and held by the compile's native project."""

import sqlbuild._native as _native
from sqlbuild.compiler.compile.types import FunctionInput, SeedInput, SourceInput
from sqlbuild.compiler.compiled_project._helpers.resource_attachment import (
    attach_functions_impl,
    attach_seeds_impl,
    attach_sources_impl,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.contracts.models import SettingsConfig, TargetConfig


def attach_resources(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    native_project: _native.NativeCompiledProject,
    settings: tuple[SettingsConfig, TargetConfig | None, str],
    no_sql_validation: bool,
    python_functions_inherit_default_namespace: bool,
) -> tuple[tuple[SeedInput, ...], tuple[FunctionInput, ...], tuple[SourceInput, ...]]:
    """Pair every seed, then attach every function and source, in that order."""

    seeds: tuple[SeedInput, ...] = attach_seeds_impl(
        discovered_inputs=discovered_inputs, native_project=native_project
    )
    functions: tuple[FunctionInput, ...] = attach_functions_impl(
        discovered_inputs=discovered_inputs,
        native_project=native_project,
        settings=settings,
        no_sql_validation=no_sql_validation,
        python_functions_inherit_default_namespace=python_functions_inherit_default_namespace,
    )
    sources: tuple[SourceInput, ...] = attach_sources_impl(
        discovered_inputs=discovered_inputs,
        native_project=native_project,
        effective_settings=settings[0],
        no_sql_validation=no_sql_validation,
    )
    return seeds, functions, sources
