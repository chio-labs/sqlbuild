"""Helpers for source loader e2e tests."""

from __future__ import annotations


def build_schema_behavior_project_files(*, source_yaml: str, loader_py: str) -> dict[str, str]:
    return {
        "sqlbuild_project.toml": (
            'name = "source_loader_schema_behavior"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "source_loader_schema_behavior.duckdb"\n'
        ),
        "sources/raw.yml": source_yaml,
        "loaders/source_rows.py": loader_py,
    }
