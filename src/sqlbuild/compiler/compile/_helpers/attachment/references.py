"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

from sqlbuild.compiler.compile.constants import TABLE_FUNCTION_RETURN_KEYS
from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
)


def build_known_ref_names(discovered_inputs: DiscoveredProjectInputs) -> set[str]:
    """Build the set of names valid as __ref() targets."""

    return {
        discovered_model_file.file_path.stem
        for discovered_model_file in discovered_inputs.model_files
    }


def build_known_seed_names(discovered_inputs: DiscoveredProjectInputs) -> set[str]:
    """Build the set of names valid as __seed() targets."""

    seed_names: set[str] = set()
    for schema_file in discovered_inputs.schema_files:
        for seed_entry in schema_file.seed_entries:
            seed_names.add(seed_entry.name)
    return seed_names


def build_known_source_names(discovered_inputs: DiscoveredProjectInputs) -> set[str]:
    """Build the set of names valid as __source() targets."""

    source_names: set[str] = set()
    for source_file in discovered_inputs.source_files:
        for source_entry in source_file.source_entries:
            source_names.add(source_entry.name)
    return source_names


def build_known_function_names(discovered_inputs: DiscoveredProjectInputs) -> set[str]:
    """Build the set of names valid as __udf() targets."""

    return {
        *(function_file.file_path.stem for function_file in discovered_inputs.sql_function_files),
        *(
            function_file.file_path.stem
            for function_file in discovered_inputs.python_function_files
        ),
    }


def build_known_table_function_names(discovered_inputs: DiscoveredProjectInputs) -> set[str]:
    """Build the set of discovered SQL functions declared as table functions."""

    return {
        function_file.file_path.stem
        for function_file in discovered_inputs.sql_function_files
        if _is_table_function_returns(function_file.header_values.get("returns"))
    }


def _is_table_function_returns(raw_returns: object) -> bool:
    return isinstance(raw_returns, dict) and set(raw_returns) == TABLE_FUNCTION_RETURN_KEYS
