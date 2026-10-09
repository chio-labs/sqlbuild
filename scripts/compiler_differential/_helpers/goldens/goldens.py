"""Golden compile outputs: one reviewable JSON file per corpus project, checked or rewritten."""

from __future__ import annotations

import json
from importlib.metadata import version
from pathlib import Path

from scripts.compiler_differential._helpers.comparing.compare import (
    as_json_object,
    first_json_difference,
)
from scripts.compiler_differential._helpers.comparing.normalize import (
    normalize_artifact_text,
    normalize_stderr,
)
from scripts.compiler_differential.constants import (
    GOLDEN_CORPUS_PREFIXES,
    GOLDEN_MANIFEST_DROPPED_KEYS,
    GOLDEN_MANIFEST_RESOURCE_SECTIONS,
    GOLDEN_MISSING_HINT,
    GOLDEN_MODE_CHECK,
    GOLDEN_OPTIONAL_CORPORA,
    GOLDEN_PATH_MASK,
    GOLDEN_RESOURCE_DROPPED_FIELDS,
    GOLDEN_SUFFIX,
    GOLDEN_VERSION_MASK,
)
from scripts.compiler_differential.models import (
    CommandOutcome,
    CorpusProject,
    Difference,
    Divergence,
    EngineRun,
)

_SQLBUILD_VERSION: str = version("sqlbuild")


def golden_differences(
    *,
    project: CorpusProject,
    runs: tuple[EngineRun, ...],
    golden_dir: Path,
    mode: str,
    masked_paths: tuple[str, ...],
) -> list[Difference]:
    """Check every run against the project's golden, or rewrite it from the first (oracle) run."""

    path: Path | None = golden_path(golden_dir=golden_dir, project=project.name)
    if path is None:
        return []
    payloads: list[dict[str, object]] = [
        golden_payload(run=run, masked_paths=masked_paths) for run in runs
    ]
    if mode != GOLDEN_MODE_CHECK:
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(golden_text(payloads[0]), encoding="utf-8")
        return []
    if not path.is_file():
        if path.parent.name in GOLDEN_OPTIONAL_CORPORA:
            return []
        return [
            Difference(
                project=project.name,
                artifact=f"golden {path.name}",
                location="file",
                left="<missing>",
                right=GOLDEN_MISSING_HINT,
                labels=("golden", "hint"),
            )
        ]
    golden: object = json.loads(path.read_text(encoding="utf-8"))
    found: list[Difference] = []
    for run, payload in zip(runs, payloads, strict=True):
        divergence: Divergence | None = first_json_difference(left=golden, right=payload)
        if divergence is not None:
            found.append(
                Difference(
                    project=project.name,
                    artifact=f"golden ({run.engine})",
                    location=divergence.location,
                    left=divergence.left,
                    right=divergence.right,
                    labels=("golden", run.engine),
                )
            )
    return found


def golden_path(*, golden_dir: Path, project: str) -> Path | None:
    """Where a corpus project's golden lives; projects outside the golden corpora have none."""

    corpus, _, name = project.partition("/")
    if corpus not in GOLDEN_CORPUS_PREFIXES or not name:
        return None
    return golden_dir / corpus / f"{name}{GOLDEN_SUFFIX}"


def golden_payload(*, run: EngineRun, masked_paths: tuple[str, ...]) -> dict[str, object]:
    """Return a run's diagnostics, compiled SQL and slimmed manifest with run noise masked."""

    return {
        "commands": [
            _command(outcome=outcome, masked_paths=masked_paths) for outcome in run.outcomes
        ],
        "compiled": {
            path: _lines(
                text=_masked(
                    text=contents.decode("utf-8", "surrogateescape"), masked_paths=masked_paths
                )
            )
            for path, contents in sorted(run.compiled.items())
        },
        "manifest": _manifest(text=run.manifest, masked_paths=masked_paths),
    }


def golden_text(payload: dict[str, object]) -> str:
    """Serialize a golden with one value per line so a changed output reads as a small diff."""

    return json.dumps(payload, indent=1, ensure_ascii=False) + "\n"


def _command(*, outcome: CommandOutcome, masked_paths: tuple[str, ...]) -> dict[str, object]:
    stdout: str = _masked(text=outcome.stdout, masked_paths=masked_paths)
    try:
        report: dict[str, object] | None = as_json_object(json.loads(stdout))
    except json.JSONDecodeError:
        report = None
    return {
        "label": outcome.label,
        "exit_code": "timed out" if outcome.timed_out else outcome.exit_code,
        "diagnostics": (
            report.get("diagnostics", [])
            if report is not None
            else _lines(
                text=normalize_stderr(_masked(text=outcome.stderr, masked_paths=masked_paths))
            )
        ),
    }


def _manifest(*, text: str | None, masked_paths: tuple[str, ...]) -> object | None:
    if text is None:
        return None
    manifest: dict[str, object] = (
        as_json_object(json.loads(_masked(text=text, masked_paths=masked_paths))) or {}
    )
    kept: dict[str, object] = {
        key: value for key, value in manifest.items() if key not in GOLDEN_MANIFEST_DROPPED_KEYS
    }
    for section in GOLDEN_MANIFEST_RESOURCE_SECTIONS:
        resources: dict[str, object] = as_json_object(kept.get(section)) or {}
        kept[section] = {name: _without_code(resource) for name, resource in resources.items()}
    return kept


def _without_code(resource: object) -> object:
    fields: dict[str, object] | None = as_json_object(resource)
    if fields is None:
        return resource
    return {
        key: value for key, value in fields.items() if key not in GOLDEN_RESOURCE_DROPPED_FIELDS
    }


def _masked(*, text: str, masked_paths: tuple[str, ...]) -> str:
    for path in masked_paths:
        text = text.replace(path, GOLDEN_PATH_MASK)
    return normalize_artifact_text(text).replace(_SQLBUILD_VERSION, GOLDEN_VERSION_MASK)


def _lines(*, text: str) -> list[str]:
    return text.split("\n")
