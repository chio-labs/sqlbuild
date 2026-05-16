"""Helpers for Dagster integration e2e tests."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from dagster import (
    AssetCheckEvaluation,
    AssetCheckSeverity,
    AssetKey,
    AssetMaterialization,
    ExecuteInProcessResult,
)

from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import REPO_ROOT


def write_sqb_capture_command(
    *, root: Path, command_log_path: Path, selector_log_path: Path
) -> tuple[str, ...]:
    """Write a wrapper that records sqb args and select-file contents before exec."""

    sqb_executable: Path = REPO_ROOT / ".venv" / "bin" / "sqb"
    script_path: Path = root / "capture_sqb.py"
    script_path.write_text(
        "\n".join(
            (
                "from __future__ import annotations",
                "import os",
                "import sys",
                "from pathlib import Path",
                f"command_log_path = Path({str(command_log_path)!r})",
                f"selector_log_path = Path({str(selector_log_path)!r})",
                f"sqb_executable = {str(sqb_executable)!r}",
                "args = sys.argv[1:]",
                "command_log_path.write_text(' '.join(args), encoding='utf-8')",
                "if '--select-file' in args:",
                "    selector_path = Path(args[args.index('--select-file') + 1])",
                "    selector_contents = selector_path.read_text(encoding='utf-8')",
                "    selector_log_path.write_text(selector_contents, encoding='utf-8')",
                "os.execv(sqb_executable, (sqb_executable, *args))",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return ("python", str(script_path))


def write_sqb_streaming_command(
    *,
    root: Path,
    started_path: Path,
    release_path: Path,
    stdout_text: str,
    json_payload: str,
) -> tuple[str, ...]:
    """Write a wrapper that emits stdout before waiting for test release."""

    script_path: Path = root / "streaming_sqb.py"
    script_path.write_text(
        "\n".join(
            (
                "from __future__ import annotations",
                "import sys",
                "import time",
                "from pathlib import Path",
                f"started_path = Path({str(started_path)!r})",
                f"release_path = Path({str(release_path)!r})",
                f"stdout_text = {stdout_text!r}",
                f"json_payload = {json_payload!r}",
                "sys.stdout.write(stdout_text)",
                "sys.stdout.flush()",
                "started_path.write_text('started', encoding='utf-8')",
                "while not release_path.exists():",
                "    time.sleep(0.01)",
                "if '--json-output' in sys.argv[1:]:",
                "    json_output_path = Path(sys.argv[sys.argv.index('--json-output') + 1])",
                "    json_output_path.write_text(json_payload, encoding='utf-8')",
                "raise SystemExit(0)",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return ("python", str(script_path))


def wait_for_captured_stdout_fragment(
    *, capsys: Any, expected_fragment: str, deadline: float
) -> str:
    """Wait until pytest capture has received a stdout fragment."""

    rendered_stdout: str = ""
    while time.monotonic() < deadline:
        rendered_stdout += capsys.readouterr().out
        if expected_fragment in rendered_stdout:
            return rendered_stdout
        time.sleep(0.01)
    return rendered_stdout


def add_failing_daily_revenue_audits(*, project_dir: Path) -> None:
    """Add one failing WARN audit and one failing ERROR audit to the copied project."""

    audits_dir: Path = project_dir / "audits" / "generic"
    audits_dir.mkdir(parents=True, exist_ok=True)
    failing_audit_sql: str = 'AUDIT ();\n\nSELECT *\nFROM __ref("@model")\nWHERE 1 = 1\n'
    (audits_dir / "forced_warning_failure.sql").write_text(
        failing_audit_sql,
        encoding="utf-8",
    )
    (audits_dir / "forced_error_failure.sql").write_text(
        failing_audit_sql,
        encoding="utf-8",
    )
    model_path: Path = project_dir / "models" / "marts" / "daily_revenue.sql"
    contents: str = model_path.read_text(encoding="utf-8")
    contents = contents.replace(
        """    expression_is_true (
      name "revenue is non-negative",
      expression "total_revenue_cents >= 0",
    ),""",
        """    expression_is_true (
      name "revenue is non-negative",
      expression "total_revenue_cents >= 0",
    ),
    forced_warning_failure (
      severity "warn",
    ),
    forced_error_failure (
      severity "error",
    ),""",
    )
    model_path.write_text(contents, encoding="utf-8")


def materialization_metadata_keys(
    *, result: ExecuteInProcessResult, asset_key: tuple[str, ...]
) -> frozenset[str]:
    """Return metadata keys for a materialized asset in a Dagster e2e result."""

    expected_asset_key: AssetKey = AssetKey(list(asset_key))
    for event in result.all_events:
        if not event.is_step_materialization:
            continue
        materialization: AssetMaterialization = event.step_materialization_data.materialization
        if materialization.asset_key == expected_asset_key:
            return frozenset(str(key) for key in materialization.metadata)
    return frozenset()


def check_names_for_asset(
    *, result: ExecuteInProcessResult, asset_key: tuple[str, ...]
) -> frozenset[str]:
    """Return Dagster check names emitted for one asset in an e2e result."""

    expected_asset_key: AssetKey = AssetKey(list(asset_key))
    names: set[str] = set()
    for event in result.all_events:
        if event.event_type_value != "ASSET_CHECK_EVALUATION":
            continue
        evaluation: AssetCheckEvaluation = event.asset_check_evaluation_data
        if evaluation is None:
            continue
        if evaluation.asset_key == expected_asset_key:
            names.add(evaluation.check_name)
    return frozenset(names)


def check_severity_for_asset(
    *, result: ExecuteInProcessResult, asset_key: tuple[str, ...], check_name: str
) -> AssetCheckSeverity | None:
    """Return Dagster-native severity for one emitted asset check."""

    expected_asset_key: AssetKey = AssetKey(list(asset_key))
    for event in result.all_events:
        if event.event_type_value != "ASSET_CHECK_EVALUATION":
            continue
        evaluation: AssetCheckEvaluation = event.asset_check_evaluation_data
        if evaluation.asset_key == expected_asset_key and evaluation.check_name == check_name:
            return evaluation.severity
    return None


def failed_check_severities_for_asset(
    *, result: ExecuteInProcessResult, asset_key: tuple[str, ...]
) -> dict[str, AssetCheckSeverity]:
    """Return failed Dagster check severities for one asset."""

    expected_asset_key: AssetKey = AssetKey(list(asset_key))
    severities: dict[str, AssetCheckSeverity] = {}
    for event in result.all_events:
        if event.event_type_value != "ASSET_CHECK_EVALUATION":
            continue
        evaluation: AssetCheckEvaluation = event.asset_check_evaluation_data
        if evaluation.asset_key == expected_asset_key and not evaluation.passed:
            severities[evaluation.check_name] = evaluation.severity
    return severities
