"""Canonical subprocess lifecycle tests for ingestr."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sqlbuild.integrations.ingestr._helpers.runner import ensure_duckdb_driver, run_ingestr_command
from sqlbuild.integrations.ingestr.exceptions import IngestrIntegrationError
from sqlbuild.observability import (
    EventDispatcher,
    LifecycleEvent,
    dispatcher_scope,
    invocation_scope,
)
from tests.unit.src.sqlbuild.integrations.ingestr._test_types import (
    IngestrDriverFailureTestCase,
    IngestrDriverTestCase,
    IngestrRunnerTestCase,
)

_RUNNER: str = "sqlbuild.integrations.ingestr._helpers.runner"
_INSTALL: tuple[str, ...] = ("dbc", "install", "--quiet", "duckdb=1.5.2")


@pytest.mark.parametrize(
    "test_case",
    (
        IngestrRunnerTestCase(
            description="signalled child excludes streams and arguments",
            returncode=-15,
            expected_signal_number=15,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_signalled_ingestr_when_run_then_safe_terminal_excludes_child_streams(
    test_case: IngestrRunnerTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    monkeypatch.setattr(
        "sqlbuild.integrations.ingestr._helpers.runner.shutil.which",
        lambda executable: executable,
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.ingestr._helpers.runner.ensure_duckdb_driver", lambda: None
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.ingestr._helpers.runner._run_ingestr_subprocess",
        lambda **kwargs: subprocess.CompletedProcess(
            args=kwargs["command"],
            returncode=test_case.returncode,
            stdout="private child stdout",
            stderr="private child stderr",
        ),
    )

    with (
        invocation_scope("inv-ingestr-signal"),
        dispatcher_scope(dispatcher),
        pytest.raises(IngestrIntegrationError, match=f"exit code {test_case.returncode}"),
    ):
        _ = run_ingestr_command(("ingestr", "--secret", "private-value"))

    assert tuple(event.event_type for event in events) == (
        "operation_started",
        "operation_failed",
    )
    assert events[0].payload == {
        "operation_kind": "subprocess",
        "operation_name": "ingestr_command",
    }
    assert events[1].payload["exit_code"] == test_case.returncode
    assert events[1].payload["signal_number"] == test_case.expected_signal_number
    assert "private" not in repr(events)


@pytest.mark.parametrize(
    "test_case",
    (
        IngestrRunnerTestCase(
            description="interrupted child has no fabricated terminal",
            returncode=0,
            expected_signal_number=0,
            expected_event_types=("operation_started",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unobserved_ingestr_interruption_when_run_then_only_start_is_published(
    test_case: IngestrRunnerTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    monkeypatch.setattr(
        "sqlbuild.integrations.ingestr._helpers.runner.shutil.which",
        lambda executable: executable,
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.ingestr._helpers.runner.ensure_duckdb_driver", lambda: None
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.ingestr._helpers.runner._run_ingestr_subprocess",
        lambda **kwargs: (_ for _ in ()).throw(KeyboardInterrupt),
    )

    with (
        invocation_scope(f"inv-{test_case.description}"),
        dispatcher_scope(dispatcher),
        pytest.raises(KeyboardInterrupt),
    ):
        _ = run_ingestr_command(("ingestr", "run"))

    assert tuple(event.event_type for event in events) == test_case.expected_event_types


@pytest.mark.parametrize(
    "test_case",
    (
        IngestrDriverTestCase(
            description="missing driver installs the duckdb package version",
            driver_files=(),
            environment={},
            expected_installs=(_INSTALL,),
        ),
        IngestrDriverTestCase(
            description="driver of another version is replaced",
            driver_files=(("duckdb.toml", "version = '2.0.0'\n"),),
            environment={},
            expected_installs=(_INSTALL,),
        ),
        IngestrDriverTestCase(
            description="matching driver is kept",
            driver_files=(("duckdb.toml", "version = '1.5.2'\n"),),
            environment={},
            expected_installs=(),
        ),
        IngestrDriverTestCase(
            description="user driver path is left alone",
            driver_files=(),
            environment={"ADBC_DRIVER_PATH": "/custom/adbc"},
            expected_installs=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_duckdb_driver_state_when_ensuring_then_installs_only_a_mismatch(
    test_case: IngestrDriverTestCase,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    driver_path: Path = tmp_path / "etc" / "adbc" / "drivers"
    driver_path.mkdir(parents=True)
    _ = [(driver_path / name).write_text(text) for name, text in test_case.driver_files]
    calls: list[tuple[tuple[str, ...], dict[str, str]]] = []
    monkeypatch.setattr(f"{_RUNNER}.sys.prefix", str(tmp_path))
    monkeypatch.setattr(f"{_RUNNER}.environ", dict(test_case.environment))
    monkeypatch.setattr(f"{_RUNNER}.metadata.version", lambda name: "1.5.2")
    monkeypatch.setattr(f"{_RUNNER}._dbc_executable", lambda: "dbc")
    monkeypatch.setattr(
        f"{_RUNNER}.subprocess.run",
        lambda args, **kwargs: (
            calls.append((args, kwargs["env"])) or subprocess.CompletedProcess(args, 0, "", "")
        ),
    )

    ensure_duckdb_driver()

    assert tuple(args for args, _ in calls) == test_case.expected_installs
    assert all(env["ADBC_DRIVER_PATH"] == str(driver_path) for _, env in calls)


@pytest.mark.parametrize(
    "test_case",
    (
        IngestrDriverFailureTestCase(
            description="failed install names the duckdb version",
            stderr="registry unreachable",
            expected_message="duckdb 1.5.2: registry unreachable",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_failing_driver_install_when_ensuring_then_names_the_duckdb_version(
    test_case: IngestrDriverFailureTestCase,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(f"{_RUNNER}.sys.prefix", str(tmp_path))
    monkeypatch.setattr(f"{_RUNNER}.environ", {})
    monkeypatch.setattr(f"{_RUNNER}.metadata.version", lambda name: "1.5.2")
    monkeypatch.setattr(f"{_RUNNER}._dbc_executable", lambda: "dbc")
    monkeypatch.setattr(
        f"{_RUNNER}.subprocess.run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 1, "", test_case.stderr),
    )

    with pytest.raises(IngestrIntegrationError, match=test_case.expected_message):
        ensure_duckdb_driver()
