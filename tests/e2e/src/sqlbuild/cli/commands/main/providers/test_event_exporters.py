"""End-to-end coverage for provider-backed lifecycle event exporters."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.providers._test_types import (
    EventExporterE2ETestCase,
    NoExporterCommandE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb


@pytest.mark.parametrize(
    "test_case",
    (EventExporterE2ETestCase("redacted provider export", "invocation_started"),),
    ids=lambda case: case.description,
)
def test_given_provider_exporter_when_building_then_receives_redacted_events_before_teardown(
    test_case: EventExporterE2ETestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path: Path = tmp_path / "exported.jsonl"
    import_path: Path = tmp_path / "exporter-imports"
    monkeypatch.setenv("EVENT_EXPORT_PATH", str(output_path))
    monkeypatch.setenv("EXPORTER_IMPORT_PATH", str(import_path))
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="event_exporter_project",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                name = "event_exporter_project"
                adapter = "duckdb"

                [connection]
                database = "event_exporter_project.duckdb"
                """
            ).strip()
            + "\n",
            "providers/event_sink.py": dedent(
                """
                import json
                import os
                from pathlib import Path

                from sqlbuild.observability import lifecycle_event_to_json
                from sqlbuild.providers import Provider

                class EventSink(Provider):
                    path: Path | None = None

                    def setup(self, ctx):
                        del ctx
                        self.path = Path(os.environ["EVENT_EXPORT_PATH"])
                        self.path.write_text("setup\\n", encoding="utf-8")

                    def write(self, event):
                        assert self.path is not None
                        with self.path.open("a", encoding="utf-8") as stream:
                            stream.write(lifecycle_event_to_json(event) + "\\n")

                    def teardown(self):
                        assert self.path is not None
                        with self.path.open("a", encoding="utf-8") as stream:
                            stream.write("teardown\\n")
                """
            ).strip()
            + "\n",
            "event_exporters/events.py": dedent(
                """
                from providers.event_sink import EventSink
                from sqlbuild.event_exporters import LifecycleEvent, event_exporter
                import os
                from pathlib import Path

                _import_path = Path(os.environ["EXPORTER_IMPORT_PATH"])
                with _import_path.open("a", encoding="utf-8") as _stream:
                    _stream.write("imported\\n")

                @event_exporter
                def export_event(event: LifecycleEvent, event_sink: EventSink) -> None:
                    event_sink.write(event)

                @event_exporter
                def failing_exporter(event: LifecycleEvent, event_sink: EventSink) -> None:
                    del event, event_sink
                    raise RuntimeError("destination credentials must not be reported")
                """
            ).strip()
            + "\n",
            "models/orders.sql": dedent(
                """
                MODEL (materialized table);

                SELECT 'do-not-export-this-sql' AS secret_value
                """
            ).strip()
            + "\n",
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    lines: list[str] = output_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "setup"
    assert lines[-1] == "teardown"
    events: list[dict[str, object]] = [json.loads(line) for line in lines[1:-1]]
    event_types: list[object] = [event["event_type"] for event in events]
    assert event_types[0] == test_case.expected_first_event
    assert event_types[-1] == "invocation_completed"
    assert "statement_completed" in event_types
    assert "do-not-export-this-sql" not in "\n".join(lines)
    assert import_path.read_text(encoding="utf-8").splitlines() == ["imported"]


@pytest.mark.parametrize(
    "test_case",
    (
        NoExporterCommandE2ETestCase("clean command", ("clean",), 0),
        NoExporterCommandE2ETestCase("skills command", ("skills", "--target", "agents"), 0),
    ),
    ids=lambda case: case.description,
)
def test_given_no_exporters_and_exploding_provider_when_non_provider_command_runs_then_succeeds(
    test_case: NoExporterCommandE2ETestCase,
    tmp_path: Path,
) -> None:
    marker_path: Path = tmp_path / "provider-imported"
    helper_marker_path: Path = tmp_path / "helper-imported"
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="no_exporter_project",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                name = "no_exporter_project"
                adapter = "duckdb"

                [connection]
                database = "no_exporter_project.duckdb"
                """
            ).lstrip(),
            "providers/exploding.py": (
                "from pathlib import Path\n"
                f"Path({str(marker_path)!r}).write_text('imported', encoding='utf-8')\n"
                "raise RuntimeError('provider must not import')\n"
            ),
            "event_exporters/helpers.py": (
                "from pathlib import Path\n"
                f"Path({str(helper_marker_path)!r}).write_text('imported', encoding='utf-8')\n"
                "def encode(value):\n    return value\n"
            ),
            "models/example.sql": "MODEL (materialized view);\n\nSELECT 1 AS value\n",
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", *test_case.command),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert not marker_path.exists()
    assert helper_marker_path.exists()
    assert not (project_dir / ".sqlbuild").exists()
