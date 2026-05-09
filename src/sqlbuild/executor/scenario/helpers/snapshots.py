"""Local scenario snapshot metadata and path helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlbuild.compiler.planner.types import ScenarioArtifactKind
from sqlbuild.executor.scenario.models import (
    ScenarioSnapshotInputSpec,
    ScenarioSnapshotManifest,
)

_SNAPSHOT_ROOT_PARTS: tuple[str, ...] = ("tests", "_scenario_snapshots")
_MANIFEST_FILE_NAME: str = "scenario.json"
_RELATION_DIRS: dict[ScenarioArtifactKind, str] = {
    ScenarioArtifactKind.SOURCE: "sources",
    ScenarioArtifactKind.REF: "refs",
    ScenarioArtifactKind.SEED: "seeds",
}


def scenario_snapshot_root(*, project_dir: Path, scenario_name: str) -> Path:
    """Return the durable snapshot root for one scenario."""

    return project_dir.joinpath(*_SNAPSHOT_ROOT_PARTS, scenario_name)


def scenario_snapshot_manifest_path(*, project_dir: Path, scenario_name: str) -> Path:
    """Return the manifest path for one scenario snapshot."""

    return (
        scenario_snapshot_root(project_dir=project_dir, scenario_name=scenario_name)
        / _MANIFEST_FILE_NAME
    )


def scenario_snapshot_relation_file_path(*, kind: ScenarioArtifactKind, logical_name: str) -> Path:
    """Return a manifest-relative JSONL path for one captured input relation."""

    relation_dir: str | None = _RELATION_DIRS.get(kind)
    if relation_dir is None:
        raise ValueError(f"Local scenario snapshots do not capture '{kind.value}' artifacts")
    return Path(relation_dir) / f"{logical_name}.jsonl"


def build_scenario_snapshot_input_fingerprint(
    *, scenario_name: str, input_specs: tuple[ScenarioSnapshotInputSpec, ...]
) -> str:
    """Build a stable fingerprint for local snapshot input compatibility."""

    payload: dict[str, object] = {
        "scenario_name": scenario_name,
        "inputs": [
            {
                "kind": spec.kind.value,
                "logical_name": spec.logical_name,
                "file_path": spec.file_path.as_posix(),
                "capture_sql": _normalize_sql(spec.capture_sql),
            }
            for spec in sorted(input_specs, key=_input_spec_sort_key)
        ],
    }
    encoded: str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def is_scenario_snapshot_fresh(
    *, manifest: ScenarioSnapshotManifest, current_input_fingerprint: str
) -> bool:
    """Return whether a stored snapshot manifest matches current input requirements."""

    return manifest.input_fingerprint == current_input_fingerprint


def _input_spec_sort_key(spec: ScenarioSnapshotInputSpec) -> tuple[str, str, str]:
    return (spec.kind.value, spec.logical_name, spec.file_path.as_posix())


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.split())
