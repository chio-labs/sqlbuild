from __future__ import annotations

from pathlib import Path

from sqlbuild.integrations.dbt.models import DbtCliConfigOverrides, DbtCliOptions, DbtCommandResult


def build_cli_overrides(
    *,
    project_dir: str | None = None,
    profiles_dir: str | None = None,
    target: str | None = None,
    target_path: str | None = None,
) -> DbtCliConfigOverrides:
    """Build dbt CLI config overrides for tests."""

    return DbtCliConfigOverrides(
        project_dir=project_dir,
        profiles_dir=profiles_dir,
        target=target,
        target_path=target_path,
    )


def build_dbt_cli_options(project_root: Path) -> DbtCliOptions:
    """Build representative dbt options for argv tests."""

    return DbtCliOptions(
        project_dir=project_root / "dbt",
        profiles_dir=project_root / "profiles",
        target="prod",
        target_path=project_root / "target/dbt",
        vars='{"run_date":"2026-01-01"}',
        state=project_root / "state",
        defer=True,
    )


class RecordingDbtInvoker:
    """Record dbt invocations and return a fixed result."""

    def __init__(self, result: DbtCommandResult) -> None:
        self.result = result
        self.calls: list[tuple[tuple[str, ...], Path | None]] = []

    def __call__(self, argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
        self.calls.append((argv, cwd))
        return self.result


def build_manifest_data(*, nodes: tuple[dict[str, object], ...]) -> dict[str, object]:
    """Build a minimal dbt manifest payload for model lookup tests."""

    return {"nodes": {str(node["unique_id"]): node for node in nodes}}


def build_manifest_model_node(
    *,
    unique_id: str,
    package_name: str,
    name: str,
    relation_name: str | None = None,
    database: str | None = None,
    schema: str | None = None,
    alias: str | None = None,
) -> dict[str, object]:
    """Build a minimal dbt manifest model node."""

    node: dict[str, object] = {
        "unique_id": unique_id,
        "resource_type": "model",
        "package_name": package_name,
        "name": name,
    }
    if relation_name is not None:
        node["relation_name"] = relation_name
    if database is not None:
        node["database"] = database
    if schema is not None:
        node["schema"] = schema
    if alias is not None:
        node["alias"] = alias
    return node
