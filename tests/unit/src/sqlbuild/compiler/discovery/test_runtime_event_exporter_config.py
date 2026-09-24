from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.exceptions import ProjectConfigError
from sqlbuild.compiler.discovery.main.runtime_extensions import discover_runtime_extensions
from sqlbuild.compiler.discovery.models import (
    DiscoveredEventExporter,
    DiscoveredRuntimeExtensions,
)
from tests.unit.src.sqlbuild.compiler.discovery._test_types import (
    EventExporterConfigTestCase,
    InvalidEventExporterConfigTestCase,
    LifecycleShutdownTimeoutTestCase,
)
from tests.unit.src.sqlbuild.compiler.discovery.helpers import write_lifecycle_event_sink_project


@pytest.mark.parametrize(
    "test_case",
    (
        EventExporterConfigTestCase(
            "global named intersection",
            "[sinks.lifecycle]\n"
            'event_kinds = ["run", "operation"]\n'
            'min_severity = "warning"\n'
            "[sinks.lifecycle.named.publish]\n"
            'event_kinds = ["run", "statement"]\n'
            'min_severity = "error"\n',
            frozenset({"run"}),
            "error",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_global_and_named_filters_when_discovering_then_effective_filter_is_intersection(
    tmp_path: Path, test_case: EventExporterConfigTestCase
) -> None:
    write_lifecycle_event_sink_project(
        project_dir=tmp_path,
        exporter_config=test_case.config,
    )

    extensions: DiscoveredRuntimeExtensions = discover_runtime_extensions(project_dir=tmp_path)

    assert extensions.command_output_sinks == ()
    assert extensions.lifecycle_shutdown_timeout_seconds is None
    exporter: DiscoveredEventExporter = extensions.event_exporters[0]
    assert exporter.event_kinds == test_case.expected_kinds
    assert exporter.min_severity == test_case.expected_min_severity


@pytest.mark.parametrize(
    "test_case",
    (
        LifecycleShutdownTimeoutTestCase("default", "", None),
        LifecycleShutdownTimeoutTestCase("zero", '[sinks.lifecycle]\nshutdown_timeout = "0s"\n', 0),
        LifecycleShutdownTimeoutTestCase(
            "seconds", '[sinks.lifecycle]\nshutdown_timeout = "30s"\n', 30
        ),
        LifecycleShutdownTimeoutTestCase(
            "upper bound", '[sinks.lifecycle]\nshutdown_timeout = "10m"\n', 600
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_lifecycle_shutdown_timeout_when_discovering_then_exposes_drain_seconds(
    tmp_path: Path, test_case: LifecycleShutdownTimeoutTestCase
) -> None:
    write_lifecycle_event_sink_project(project_dir=tmp_path, exporter_config=test_case.config)

    extensions: DiscoveredRuntimeExtensions = discover_runtime_extensions(project_dir=tmp_path)

    assert extensions.lifecycle_shutdown_timeout_seconds == test_case.expected_seconds
    assert len(extensions.event_exporters) == 1


@pytest.mark.parametrize(
    "test_case",
    (
        InvalidEventExporterConfigTestCase(
            "unknown lifecycle sink",
            '[sinks.lifecycle.named.missing]\nmin_severity = "info"\n',
            "unknown sink",
        ),
        InvalidEventExporterConfigTestCase(
            "unknown kind", '[sinks.lifecycle]\nevent_kinds = ["kafka"]\n', "unknown kind"
        ),
        InvalidEventExporterConfigTestCase(
            "unknown severity",
            '[sinks.lifecycle]\nmin_severity = "fatal"\n',
            "min_severity",
        ),
        InvalidEventExporterConfigTestCase(
            "global typo",
            "[sinks.lifecycle]\nevent_kind = []\n",
            "unknown key.*event_kind",
        ),
        InvalidEventExporterConfigTestCase(
            "named typo",
            '[sinks.lifecycle.named.publish]\nminimum_severity = "info"\n',
            "unknown key.*minimum_severity",
        ),
        InvalidEventExporterConfigTestCase(
            "negative shutdown timeout",
            '[sinks.lifecycle]\nshutdown_timeout = "-1s"\n',
            "sinks.lifecycle.shutdown_timeout must be a fixed duration from '0s' to '10m'",
        ),
        InvalidEventExporterConfigTestCase(
            "numeric shutdown timeout",
            "[sinks.lifecycle]\nshutdown_timeout = 5\n",
            "sinks.lifecycle.shutdown_timeout must be a fixed duration",
        ),
        InvalidEventExporterConfigTestCase(
            "calendar shutdown timeout",
            '[sinks.lifecycle]\nshutdown_timeout = "1mo"\n',
            "sinks.lifecycle.shutdown_timeout must be a fixed duration",
        ),
        InvalidEventExporterConfigTestCase(
            "shutdown timeout above upper bound",
            '[sinks.lifecycle]\nshutdown_timeout = "11m"\n',
            "sinks.lifecycle.shutdown_timeout must be a fixed duration",
        ),
        InvalidEventExporterConfigTestCase(
            "named shutdown timeout",
            '[sinks.lifecycle.named.publish]\nshutdown_timeout = "5s"\n',
            "unknown key.*shutdown_timeout",
        ),
        InvalidEventExporterConfigTestCase(
            "legacy exporter config",
            '[event_exporters]\nmin_severity = "info"\n',
            "replaced by sinks.lifecycle",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_runtime_filter_when_discovering_then_fails_before_execution(
    tmp_path: Path, test_case: InvalidEventExporterConfigTestCase
) -> None:
    write_lifecycle_event_sink_project(project_dir=tmp_path, exporter_config=test_case.config)

    with pytest.raises(ProjectConfigError, match=test_case.expected_error):
        discover_runtime_extensions(project_dir=tmp_path)
