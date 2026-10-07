"""Compare everything two engines produced for one project and report first differences."""

from __future__ import annotations

import json
from collections.abc import Callable

from scripts.compiler_differential._helpers.comparing.compare import (
    as_json_object,
    first_document_difference,
    first_json_difference,
    first_text_difference,
)
from scripts.compiler_differential._helpers.comparing.normalize import (
    normalize_artifact_text,
    normalize_stderr,
    strip_manifest_metadata,
    strip_report_fields,
)
from scripts.compiler_differential.constants import (
    MISSING_VALUE,
    MODEL_RESOURCE_TYPE,
    PLAN_LABEL,
)
from scripts.compiler_differential.models import (
    CommandOutcome,
    Difference,
    Divergence,
    EngineRun,
)


def compare_engine_runs(*, project: str, left: EngineRun, right: EngineRun) -> list[Difference]:
    """Return the first difference in every artifact that differs between two engine runs."""

    found: list[tuple[str, Divergence | None]] = []
    for left_outcome, right_outcome in zip(left.outcomes, right.outcomes, strict=True):
        found.extend(_command_differences(left=left_outcome, right=right_outcome))
    found.extend(_tree_differences(left=left.compiled, right=right.compiled))
    found.append(
        (
            "target/manifest.json",
            _optional_json_difference(
                left=left.manifest, right=right.manifest, strip=strip_manifest_metadata
            ),
        )
    )
    found.append(
        (
            "target/sqlbuild_dag.json",
            _optional_json_difference(left=left.dag, right=right.dag, strip=None),
        )
    )
    found.extend(
        (f"query fingerprint of model {model}", divergence)
        for model, divergence in _fingerprint_differences(left=left, right=right)
    )
    found.extend(_capture_differences(left=left.captures, right=right.captures))
    return [
        Difference(
            project=project,
            artifact=artifact,
            location=divergence.location,
            left=divergence.left,
            right=divergence.right,
        )
        for artifact, divergence in found
        if divergence is not None
    ]


def diagnostic_codes(*, outcome: CommandOutcome, severity: str | None) -> tuple[str, ...]:
    """Return a JSON compile report's diagnostic codes in order, optionally of one severity."""

    payload: dict[str, object] = as_json_object(_loads(outcome.stdout)) or {}
    diagnostics: object = payload.get("diagnostics")
    found: list[str] = []
    for raw_diagnostic in diagnostics if isinstance(diagnostics, list) else ():
        diagnostic: dict[str, object] | None = as_json_object(raw_diagnostic)
        if diagnostic is not None and (severity is None or diagnostic.get("severity") == severity):
            found.append(str(diagnostic.get("code")))
    return tuple(found)


def _command_differences(
    *, left: CommandOutcome, right: CommandOutcome
) -> list[tuple[str, Divergence | None]]:
    label: str = f"`{left.label}`"
    exit_codes: Divergence | None = (
        None
        if (left.exit_code, left.timed_out) == (right.exit_code, right.timed_out)
        else Divergence(
            location="exit code",
            left=_exit_label(left),
            right=_exit_label(right),
        )
    )
    return [
        (f"{label} exit code", exit_codes),
        (f"{label} stdout", _stdout_difference(left=left.stdout, right=right.stdout)),
        (
            f"{label} stderr",
            first_text_difference(
                left=normalize_stderr(left.stderr), right=normalize_stderr(right.stderr)
            ),
        ),
    ]


def _exit_label(outcome: CommandOutcome) -> str:
    return "timed out" if outcome.timed_out else str(outcome.exit_code)


def _stdout_difference(*, left: str, right: str) -> Divergence | None:
    normalized_left: str = normalize_artifact_text(left)
    normalized_right: str = normalize_artifact_text(right)
    try:
        left_payload: object = json.loads(normalized_left)
        right_payload: object = json.loads(normalized_right)
    except json.JSONDecodeError:
        return first_text_difference(left=normalized_left, right=normalized_right)
    return first_json_difference(
        left=strip_report_fields(left_payload), right=strip_report_fields(right_payload)
    )


def _tree_differences(
    *, left: dict[str, bytes], right: dict[str, bytes]
) -> list[tuple[str, Divergence | None]]:
    differences: list[tuple[str, Divergence | None]] = []
    for path in sorted(set(left) | set(right)):
        artifact: str = f"target/compiled/{path}"
        if path not in left or path not in right:
            differences.append(
                (
                    artifact,
                    _presence_divergence(left_present=path in left, right_present=path in right),
                )
            )
            continue
        differences.append(
            (
                artifact,
                first_text_difference(
                    left=normalize_artifact_text(left[path].decode("utf-8", "surrogateescape")),
                    right=normalize_artifact_text(right[path].decode("utf-8", "surrogateescape")),
                ),
            )
        )
    return differences


def _optional_json_difference(
    *, left: str | None, right: str | None, strip: Callable[[object], object] | None
) -> Divergence | None:
    if left is None or right is None:
        if left is None and right is None:
            return None
        return _presence_divergence(left_present=left is not None, right_present=right is not None)
    try:
        left_payload: object = json.loads(normalize_artifact_text(left))
        right_payload: object = json.loads(normalize_artifact_text(right))
    except json.JSONDecodeError:
        return first_text_difference(left=left, right=right)
    if strip is not None:
        left_payload = strip(left_payload)
        right_payload = strip(right_payload)
    return first_json_difference(left=left_payload, right=right_payload)


def _fingerprint_differences(
    *, left: EngineRun, right: EngineRun
) -> list[tuple[str, Divergence | None]]:
    left_fingerprints: dict[str, str] = _model_fingerprints(left)
    right_fingerprints: dict[str, str] = _model_fingerprints(right)
    return [
        (
            model,
            None
            if left_fingerprints.get(model) == right_fingerprints.get(model)
            else Divergence(
                location="fingerprint",
                left=left_fingerprints.get(model, MISSING_VALUE),
                right=right_fingerprints.get(model, MISSING_VALUE),
            ),
        )
        for model in sorted(set(left_fingerprints) | set(right_fingerprints))
    ]


def _model_fingerprints(run: EngineRun) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    manifest: dict[str, object] = as_json_object(_loads(run.manifest)) or {}
    nodes: dict[str, object] = as_json_object(manifest.get("nodes")) or {}
    for raw_node in nodes.values():
        node: dict[str, object] = as_json_object(raw_node) or {}
        checksum: dict[str, object] | None = as_json_object(node.get("checksum"))
        if checksum is not None and node.get("resource_type") == MODEL_RESOURCE_TYPE:
            fingerprints[f"{node.get('name')} (manifest query hash)"] = str(
                checksum.get("checksum")
            )
    for outcome in run.outcomes:
        plan: dict[str, object] = (
            as_json_object(_loads(outcome.stdout)) or {} if outcome.label == PLAN_LABEL else {}
        )
        models: object = plan.get("models")
        for raw_model in models if isinstance(models, list) else ():
            model: dict[str, object] | None = as_json_object(raw_model)
            if model is not None:
                fingerprints[f"{model.get('name')} (plan version hash)"] = str(
                    model.get("expected_version_hash")
                )
    return fingerprints


def _loads(text: str | None) -> object:
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _capture_differences(
    *, left: dict[str, dict[str, str]], right: dict[str, dict[str, str]]
) -> list[tuple[str, Divergence | None]]:
    differences: list[tuple[str, Divergence | None]] = []
    for command in sorted(set(left) | set(right)):
        left_files: dict[str, str] = left.get(command, {})
        right_files: dict[str, str] = right.get(command, {})
        for name in sorted(set(left_files) | set(right_files)):
            artifact: str = f"stage capture {command}/{name}"
            if name not in left_files or name not in right_files:
                differences.append(
                    (
                        artifact,
                        _presence_divergence(
                            left_present=name in left_files, right_present=name in right_files
                        ),
                    )
                )
                continue
            differences.append(
                (
                    artifact,
                    first_document_difference(
                        left=normalize_artifact_text(left_files[name]),
                        right=normalize_artifact_text(right_files[name]),
                    ),
                )
            )
    return differences


def _presence_divergence(*, left_present: bool, right_present: bool) -> Divergence:
    return Divergence(
        location="file",
        left="present" if left_present else MISSING_VALUE,
        right="present" if right_present else MISSING_VALUE,
    )
