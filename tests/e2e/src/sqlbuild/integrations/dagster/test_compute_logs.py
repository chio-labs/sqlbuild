from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.integrations.dagster._test_types import (
    DagsterComputeLogE2ETestCase,
)
from tests.e2e.src.sqlbuild.integrations.dagster.helpers import dagster_compute_log_job_source


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterComputeLogE2ETestCase(
            description="live asset events preserve full multiprocess Dagster compute stdout",
            expected_stdout_fragments=(
                "PROGRESS LINE",
                "SELECT * FROM important_table;",
            ),
            unexpected_structured_log_fragment="SQLBuild:     SELECT * FROM important_table;",
            expected_materialization_fragment="Materialized value orders",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_verbose_sqlbuild_stream_when_dagster_captures_logs_then_stdout_remains_complete(
    test_case: DagsterComputeLogE2ETestCase,
    tmp_path: Path,
) -> None:
    dagster_home: Path = tmp_path / "dagster-home"
    compute_dir: Path = dagster_home / "compute"
    history_dir: Path = dagster_home / "history"
    compute_dir.mkdir(parents=True)
    history_dir.mkdir()
    (dagster_home / "dagster.yaml").write_text(
        "storage:\n"
        "  sqlite:\n"
        f"    base_dir: {history_dir}\n"
        "compute_logs:\n"
        "  module: dagster._core.storage.local_compute_log_manager\n"
        "  class: LocalComputeLogManager\n"
        "  config:\n"
        f"    base_dir: {compute_dir}\n"
        "telemetry:\n"
        "  enabled: false\n",
        encoding="utf-8",
    )
    job_file: Path = tmp_path / "stdout_job.py"
    job_file.write_text(dagster_compute_log_job_source(root=tmp_path), encoding="utf-8")
    environment: dict[str, str] = dict(os.environ)
    environment["DAGSTER_HOME"] = str(dagster_home)

    completed: subprocess.CompletedProcess[str] = subprocess.run(
        [
            str(Path(sys.executable).parent / "dagster"),
            "job",
            "execute",
            "-f",
            str(job_file),
            "-a",
            "defs",
            "-j",
            "stdout_capture_job",
        ],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    combined_output: str = completed.stdout + completed.stderr
    assert completed.returncode == 0, combined_output
    stdout_files: tuple[Path, ...] = tuple(compute_dir.glob("**/*.out"))
    assert len(stdout_files) == 1
    compute_stdout: str = stdout_files[0].read_text(encoding="utf-8")
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in compute_stdout
    assert test_case.unexpected_structured_log_fragment not in combined_output
    assert test_case.expected_materialization_fragment in combined_output
