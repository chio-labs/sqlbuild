"""Local scenario snapshot metadata and path helpers."""

from __future__ import annotations

import hashlib
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from sqlbuild.compiler.planner.models import (
    ScenarioExecutionPlan,
    ScenarioFixturePlan,
    SeedPlanEntry,
)
from sqlbuild.compiler.planner.types import ScenarioArtifactKind
from sqlbuild.executor.scenario.models import (
    ScenarioSnapshotCapturePlan,
    ScenarioSnapshotCaptureRelationPlan,
    ScenarioSnapshotColumn,
    ScenarioSnapshotFileStats,
    ScenarioSnapshotInputSpec,
    ScenarioSnapshotManifest,
    ScenarioSnapshotRelation,
    ScenarioSnapshotStateResult,
)
from sqlbuild.executor.scenario.types import ScenarioSnapshotState

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


def build_scenario_snapshot_input_specs(
    *, scenario_plan: ScenarioExecutionPlan
) -> tuple[ScenarioSnapshotInputSpec, ...]:
    """Return durable local snapshot input requirements for one scenario plan."""

    specs: list[ScenarioSnapshotInputSpec] = []
    fixture_plan: ScenarioFixturePlan
    for fixture_plan in scenario_plan.fixture_plans:
        specs.append(
            ScenarioSnapshotInputSpec(
                kind=fixture_plan.kind,
                logical_name=fixture_plan.logical_name,
                file_path=scenario_snapshot_relation_file_path(
                    kind=fixture_plan.kind,
                    logical_name=fixture_plan.logical_name,
                ),
                capture_sql=fixture_plan.sql,
            )
        )

    seed_entry: SeedPlanEntry
    for seed_entry in scenario_plan.seed_entries:
        specs.append(
            ScenarioSnapshotInputSpec(
                kind=ScenarioArtifactKind.SEED,
                logical_name=seed_entry.name,
                file_path=scenario_snapshot_relation_file_path(
                    kind=ScenarioArtifactKind.SEED,
                    logical_name=seed_entry.name,
                ),
                capture_sql=f"seed_file:{seed_entry.file_path.as_posix()}",
            )
        )

    return tuple(sorted(specs, key=_input_spec_sort_key))


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


def write_scenario_snapshot_manifest(
    *, manifest_path: Path, manifest: ScenarioSnapshotManifest
) -> None:
    """Write one local scenario snapshot manifest as stable JSON."""

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(_manifest_to_json_data(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_scenario_snapshot_manifest(*, manifest_path: Path) -> ScenarioSnapshotManifest:
    """Read one local scenario snapshot manifest from JSON."""

    try:
        raw_data: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(raw_data, dict):
            raise ValueError("manifest root must be a JSON object")
        return _manifest_from_json_data(raw_data)
    except JSONDecodeError as exc:
        raise ValueError(f"Invalid scenario snapshot manifest JSON: {exc.msg}") from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid scenario snapshot manifest: {exc}") from exc


def classify_scenario_snapshot_state(
    *, project_dir: Path, scenario_plan: ScenarioExecutionPlan
) -> ScenarioSnapshotStateResult:
    """Return whether a local scenario snapshot is fresh, missing, stale, or invalid."""

    manifest_path: Path = scenario_snapshot_manifest_path(
        project_dir=project_dir,
        scenario_name=scenario_plan.name,
    )
    if not manifest_path.exists():
        return ScenarioSnapshotStateResult(
            state=ScenarioSnapshotState.MISSING,
            manifest_path=manifest_path,
        )

    try:
        manifest: ScenarioSnapshotManifest = read_scenario_snapshot_manifest(
            manifest_path=manifest_path,
        )
    except ValueError as exc:
        return ScenarioSnapshotStateResult(
            state=ScenarioSnapshotState.INVALID,
            manifest_path=manifest_path,
            error_message=str(exc),
        )

    current_fingerprint: str = build_scenario_snapshot_input_fingerprint(
        scenario_name=scenario_plan.name,
        input_specs=build_scenario_snapshot_input_specs(scenario_plan=scenario_plan),
    )
    state: ScenarioSnapshotState = (
        ScenarioSnapshotState.FRESH
        if is_scenario_snapshot_fresh(
            manifest=manifest,
            current_input_fingerprint=current_fingerprint,
        )
        else ScenarioSnapshotState.STALE
    )
    return ScenarioSnapshotStateResult(
        state=state,
        manifest_path=manifest_path,
        manifest=manifest,
    )


def build_scenario_snapshot_capture_plan(
    *, project_dir: Path, scenario_plan: ScenarioExecutionPlan
) -> ScenarioSnapshotCapturePlan:
    """Build executor-side local snapshot capture work from one scenario execution plan."""

    input_specs: tuple[ScenarioSnapshotInputSpec, ...] = build_scenario_snapshot_input_specs(
        scenario_plan=scenario_plan,
    )
    relation_plans: list[ScenarioSnapshotCaptureRelationPlan] = []
    spec_by_identity: dict[tuple[ScenarioArtifactKind, str], ScenarioSnapshotInputSpec] = {
        (spec.kind, spec.logical_name): spec for spec in input_specs
    }

    fixture_plan: ScenarioFixturePlan
    for fixture_plan in scenario_plan.fixture_plans:
        spec: ScenarioSnapshotInputSpec = spec_by_identity[
            (fixture_plan.kind, fixture_plan.logical_name)
        ]
        relation_plans.append(
            ScenarioSnapshotCaptureRelationPlan(
                kind=fixture_plan.kind,
                logical_name=fixture_plan.logical_name,
                source_target=fixture_plan.target,
                file_path=spec.file_path,
                capture_sql=spec.capture_sql,
            )
        )

    seed_entry: SeedPlanEntry
    for seed_entry in scenario_plan.seed_entries:
        spec = spec_by_identity[(ScenarioArtifactKind.SEED, seed_entry.name)]
        relation_plans.append(
            ScenarioSnapshotCaptureRelationPlan(
                kind=ScenarioArtifactKind.SEED,
                logical_name=seed_entry.name,
                source_target=seed_entry.target,
                file_path=spec.file_path,
                capture_sql=spec.capture_sql,
            )
        )

    return ScenarioSnapshotCapturePlan(
        scenario_name=scenario_plan.name,
        snapshot_root=scenario_snapshot_root(
            project_dir=project_dir,
            scenario_name=scenario_plan.name,
        ),
        manifest_path=scenario_snapshot_manifest_path(
            project_dir=project_dir,
            scenario_name=scenario_plan.name,
        ),
        input_fingerprint=build_scenario_snapshot_input_fingerprint(
            scenario_name=scenario_plan.name,
            input_specs=input_specs,
        ),
        relations=tuple(sorted(relation_plans, key=_capture_relation_sort_key)),
    )


def build_scenario_snapshot_manifest_shell(
    *,
    capture_plan: ScenarioSnapshotCapturePlan,
    captured_at: str,
    capture_adapter: str,
    capture_dialect: str,
    sqlbuild_version: str,
) -> ScenarioSnapshotManifest:
    """Build a zero-row manifest shell for a capture plan before rows are downloaded."""

    return ScenarioSnapshotManifest(
        version=1,
        scenario_name=capture_plan.scenario_name,
        captured_at=captured_at,
        capture_adapter=capture_adapter,
        capture_dialect=capture_dialect,
        sqlbuild_version=sqlbuild_version,
        input_fingerprint=capture_plan.input_fingerprint,
        total_rows=0,
        total_bytes=0,
        relations=tuple(
            ScenarioSnapshotRelation(
                kind=relation.kind,
                logical_name=relation.logical_name,
                file_path=relation.file_path,
                row_count=0,
                byte_count=0,
            )
            for relation in capture_plan.relations
        ),
    )


def write_scenario_snapshot_jsonl(
    *, file_path: Path, rows: tuple[dict[str, object], ...]
) -> ScenarioSnapshotFileStats:
    """Write JSON object rows as newline-delimited JSON and return file statistics."""

    file_path.parent.mkdir(parents=True, exist_ok=True)
    row_count: int = 0
    byte_count: int = 0
    with file_path.open("w", encoding="utf-8") as snapshot_file:
        row: dict[str, object]
        for row in rows:
            encoded_row: str = json.dumps(row, sort_keys=True, separators=(",", ":"))
            snapshot_file.write(encoded_row)
            snapshot_file.write("\n")
            row_count += 1
            byte_count += len(encoded_row.encode("utf-8")) + 1
    return ScenarioSnapshotFileStats(row_count=row_count, byte_count=byte_count)


def read_scenario_snapshot_jsonl(*, file_path: Path) -> tuple[dict[str, object], ...]:
    """Read newline-delimited JSON object rows from one local scenario snapshot file."""

    rows: list[dict[str, object]] = []
    with file_path.open("r", encoding="utf-8") as snapshot_file:
        line_number: int
        line: str
        for line_number, line in enumerate(snapshot_file, start=1):
            stripped_line: str = line.strip()
            if stripped_line == "":
                continue
            try:
                row: Any = json.loads(stripped_line)
            except JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid scenario snapshot JSONL at line {line_number}: {exc.msg}"
                ) from exc
            if not isinstance(row, dict):
                raise ValueError(
                    f"Invalid scenario snapshot JSONL at line {line_number}: "
                    "row must be a JSON object"
                )
            rows.append(row)
    return tuple(rows)


def is_scenario_snapshot_fresh(
    *, manifest: ScenarioSnapshotManifest, current_input_fingerprint: str
) -> bool:
    """Return whether a stored snapshot manifest matches current input requirements."""

    return manifest.input_fingerprint == current_input_fingerprint


def _input_spec_sort_key(spec: ScenarioSnapshotInputSpec) -> tuple[str, str, str]:
    return (spec.kind.value, spec.logical_name, spec.file_path.as_posix())


def _capture_relation_sort_key(
    relation: ScenarioSnapshotCaptureRelationPlan,
) -> tuple[str, str, str]:
    return (relation.kind.value, relation.logical_name, relation.file_path.as_posix())


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.split())


def _manifest_to_json_data(manifest: ScenarioSnapshotManifest) -> dict[str, object]:
    return {
        "version": manifest.version,
        "scenario_name": manifest.scenario_name,
        "captured_at": manifest.captured_at,
        "capture_adapter": manifest.capture_adapter,
        "capture_dialect": manifest.capture_dialect,
        "sqlbuild_version": manifest.sqlbuild_version,
        "input_fingerprint": manifest.input_fingerprint,
        "format": manifest.format,
        "total_rows": manifest.total_rows,
        "total_bytes": manifest.total_bytes,
        "relations": [
            {
                "kind": relation.kind.value,
                "logical_name": relation.logical_name,
                "file": relation.file_path.as_posix(),
                "row_count": relation.row_count,
                "bytes": relation.byte_count,
                "columns": [
                    {
                        "name": column.name,
                        "warehouse_type": column.warehouse_type,
                        "local_type": column.local_type,
                    }
                    for column in relation.columns
                ],
            }
            for relation in manifest.relations
        ],
    }


def _manifest_from_json_data(data: dict[str, Any]) -> ScenarioSnapshotManifest:
    relations_data: Any = data.get("relations", [])
    if not isinstance(relations_data, list):
        raise ValueError("relations must be a list")
    return ScenarioSnapshotManifest(
        version=int(data["version"]),
        scenario_name=str(data["scenario_name"]),
        captured_at=str(data["captured_at"]),
        capture_adapter=str(data["capture_adapter"]),
        capture_dialect=str(data["capture_dialect"]),
        sqlbuild_version=str(data["sqlbuild_version"]),
        input_fingerprint=str(data["input_fingerprint"]),
        total_rows=int(data["total_rows"]),
        total_bytes=int(data["total_bytes"]),
        relations=tuple(_relation_from_json_data(relation) for relation in relations_data),
        format=str(data.get("format", "jsonl")),
    )


def _relation_from_json_data(data: Any) -> ScenarioSnapshotRelation:
    if not isinstance(data, dict):
        raise ValueError("relation entries must be JSON objects")
    columns_data: Any = data.get("columns", [])
    if not isinstance(columns_data, list):
        raise ValueError("relation columns must be a list")
    return ScenarioSnapshotRelation(
        kind=ScenarioArtifactKind(str(data["kind"])),
        logical_name=str(data["logical_name"]),
        file_path=Path(str(data["file"])),
        row_count=int(data["row_count"]),
        byte_count=int(data["bytes"]),
        columns=tuple(_column_from_json_data(column) for column in columns_data),
    )


def _column_from_json_data(data: Any) -> ScenarioSnapshotColumn:
    if not isinstance(data, dict):
        raise ValueError("column entries must be JSON objects")
    return ScenarioSnapshotColumn(
        name=str(data["name"]),
        warehouse_type=str(data["warehouse_type"]),
        local_type=str(data["local_type"]),
    )
