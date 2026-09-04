"""Command-scope output capture activation and context tests."""

from __future__ import annotations

import io
import sys

import pytest

from sqlbuild.cli.commands.main.entrypoint._dispatch_with_output_capture import (
    configured_output_capture_scope,
)
from sqlbuild.observability import ExecutionIdentity
from sqlbuild.output_capture import output_capture_context
from sqlbuild.runtime.event_exporting.classes.command_scope import EventExporterCommandScope
from sqlbuild.runtime.output_capture.models import OutputRecord
from tests.unit.src.sqlbuild.cli.commands.main.entrypoint._test_types import (
    OutputCaptureWiringTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.entrypoint.helpers import make_event_exporter_scope


@pytest.mark.parametrize(
    "test_case",
    (
        OutputCaptureWiringTestCase(
            description="inert_without_event_export_config", expected_success=True
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_no_event_export_configuration_when_dispatching_then_capture_is_inert(
    test_case: OutputCaptureWiringTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert test_case.expected_success is True
    sink: io.StringIO = io.StringIO()
    monkeypatch.setattr(sys, "stdout", sink)

    with configured_output_capture_scope(
        exporter_scope=None,
        identity=ExecutionIdentity(invocation_id="invocation-1"),
    ):
        print("terminal only")

    assert sink.getvalue() == "terminal only\n"
    assert sys.stdout is sink


@pytest.mark.parametrize(
    "test_case",
    (OutputCaptureWiringTestCase(description="configured_event_export", expected_success=True),),
    ids=lambda case: case.description,
)
def test_given_event_export_configuration_when_dispatching_then_output_uses_same_exporter_scope(
    test_case: OutputCaptureWiringTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert test_case.expected_success is True
    stdout: io.StringIO = io.StringIO()
    stderr: io.StringIO = io.StringIO()
    records: list[OutputRecord] = []
    exporter_scope: EventExporterCommandScope = make_event_exporter_scope(records=records)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    with configured_output_capture_scope(
        exporter_scope=exporter_scope,
        identity=ExecutionIdentity(invocation_id="invocation-1", run_id="run-1"),
    ):
        print("normal")
        print("warning", file=sys.stderr)
    _ = exporter_scope.close()

    assert stdout.getvalue() == "normal\n"
    assert stderr.getvalue() == "warning\n"
    assert tuple(record.message for record in records) == ("normal\n", "warning\n")
    assert tuple(record.sequence for record in records) == (0, 1)
    assert records[0].external_context == {}


@pytest.mark.parametrize(
    "test_case",
    (OutputCaptureWiringTestCase(description="optional_external_context", expected_success=True),),
    ids=lambda case: case.description,
)
def test_given_integration_context_when_event_export_is_configured_then_context_is_stamped_opaquely(
    test_case: OutputCaptureWiringTestCase,
) -> None:
    assert test_case.expected_success is True
    records: list[OutputRecord] = []
    exporter_scope: EventExporterCommandScope = make_event_exporter_scope(records=records)

    with output_capture_context(external_context={"system": "opaque", "external_run": "42"}):
        with configured_output_capture_scope(
            exporter_scope=exporter_scope,
            identity=ExecutionIdentity(invocation_id="invocation-1"),
        ):
            print("context line")
    _ = exporter_scope.close()

    assert records[0].external_context == {"system": "opaque", "external_run": "42"}


@pytest.mark.parametrize(
    "test_case",
    (OutputCaptureWiringTestCase(description="interrupted_cleanup", expected_success=True),),
    ids=lambda case: case.description,
)
def test_given_interrupted_command_when_cleaning_up_then_stream_restores_and_interrupt_propagates(
    test_case: OutputCaptureWiringTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert test_case.expected_success is True
    stdout: io.StringIO = io.StringIO()
    records: list[OutputRecord] = []
    exporter_scope: EventExporterCommandScope = make_event_exporter_scope(records=records)
    monkeypatch.setattr(sys, "stdout", stdout)

    with pytest.raises(KeyboardInterrupt):
        with configured_output_capture_scope(
            exporter_scope=exporter_scope,
            identity=ExecutionIdentity(invocation_id="invocation-1"),
        ):
            print("before interrupt")
            raise KeyboardInterrupt
    _ = exporter_scope.close()

    assert stdout.getvalue() == "before interrupt\n"
    assert tuple(record.message for record in records) == ("before interrupt\n",)
    assert sys.stdout is stdout


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
