"""Custom rules split across host processes report exactly what one host reports."""

import time
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.rule_engine._helpers.host import custom_host, custom_host_pool
from sqlbuild.rule_engine.constants import CUSTOM_RULES_CACHE_FILE
from sqlbuild.rule_engine.exceptions import HostCancelledError, RulesError
from sqlbuild.rule_engine.models import CustomRulesOutcome
from tests.unit.src.sqlbuild.rule_engine._helpers.host._test_types import (
    AwaitInputsTestCase,
    AwaitPublishedInputsTestCase,
    HostCancellationTestCase,
    HostFailureTestCase,
    HostInputsTestCase,
    HostPartitionTestCase,
    HostPlanTestCase,
)
from tests.unit.src.sqlbuild.rule_engine._helpers.host.helpers import (
    delay_inputs,
    evaluate_order_rules,
    fail_inputs,
    fail_inputs_without_directory,
    orders_project,
    record_signals,
    touch_files,
    use_hosts,
    write_order_rules,
)


@pytest.mark.parametrize(
    "test_case",
    [
        HostPartitionTestCase(
            description="three hosts", model_count=7, hosts=3, expected_host_runs=3
        ),
        HostPartitionTestCase(
            description="more hosts than subjects", model_count=2, hosts=8, expected_host_runs=3
        ),
        HostPartitionTestCase(
            description="module state reruns the rule in one host",
            model_count=7,
            hosts=3,
            expected_host_runs=4,
            records_module_state=True,
        ),
        HostPartitionTestCase(
            description="cross-model duplicate detector reruns in one host",
            model_count=7,
            hosts=3,
            expected_host_runs=4,
            detects_duplicates=True,
        ),
        HostPartitionTestCase(
            description="uncached cross-model duplicate detector reruns in one host",
            model_count=7,
            hosts=3,
            expected_host_runs=4,
            detects_duplicates=True,
            cache_enabled=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_partitioned_hosts_when_evaluating_then_findings_and_cache_match_one_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: HostPartitionTestCase
) -> None:
    write_order_rules(
        root=tmp_path,
        records_module_state=test_case.records_module_state,
        detects_duplicates=test_case.detects_duplicates,
    )
    project: CompiledProject = orders_project(model_count=test_case.model_count)
    cache_path: Path = tmp_path / CUSTOM_RULES_CACHE_FILE
    cache_glob: str = CUSTOM_RULES_CACHE_FILE
    cache_enabled: bool = test_case.cache_enabled

    single_launches: list[str] = use_hosts(monkeypatch=monkeypatch, hosts=1)
    single: CustomRulesOutcome = evaluate_order_rules(
        project=project, root=tmp_path, cache_enabled=cache_enabled
    )
    single_warm: CustomRulesOutcome = evaluate_order_rules(
        project=project, root=tmp_path, cache_enabled=cache_enabled
    )
    single_cache: bytes = b"".join(path.read_bytes() for path in tmp_path.glob(cache_glob))
    cache_path.unlink(missing_ok=True)
    monkeypatch.undo()
    split_launches: list[str] = use_hosts(monkeypatch=monkeypatch, hosts=test_case.hosts)
    split: CustomRulesOutcome = evaluate_order_rules(
        project=project, root=tmp_path, cache_enabled=cache_enabled
    )
    split_cold_launches: int = len(split_launches)
    split_cache: bytes = b"".join(path.read_bytes() for path in tmp_path.glob(cache_glob))
    split_warm: CustomRulesOutcome = evaluate_order_rules(
        project=project, root=tmp_path, cache_enabled=cache_enabled
    )

    assert split.findings == single.findings
    assert split_warm.findings == single_warm.findings == single.findings
    assert len(single_launches) == 1 + int(not cache_enabled)
    assert split_cold_launches == test_case.expected_host_runs
    assert (split.cache_hits, split.cache_misses) == (single.cache_hits, single.cache_misses)
    assert (split_warm.cache_hits, split_warm.cache_misses) == (
        single_warm.cache_hits,
        single_warm.cache_misses,
    )
    assert split_cache == single_cache
    assert bool(single_cache) is cache_enabled
    assert not tuple((tmp_path / "target" / "rules-cache" / "host-inputs").iterdir())


@pytest.mark.parametrize(
    "test_case",
    [
        HostPartitionTestCase(
            description="edit after split", model_count=6, hosts=3, expected_host_runs=3
        )
    ],
    ids=lambda case: case.description,
)
def test_given_results_cached_by_split_hosts_when_rerunning_then_only_edited_subjects_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: HostPartitionTestCase
) -> None:
    write_order_rules(root=tmp_path)
    project: CompiledProject = orders_project(model_count=test_case.model_count)
    edited: CompiledProject = orders_project(
        model_count=test_case.model_count, edits={"orders_003": "SELECT 2 AS order_id"}
    )
    launches: list[str] = use_hosts(monkeypatch=monkeypatch, hosts=test_case.hosts)

    cold: CustomRulesOutcome = evaluate_order_rules(project=project, root=tmp_path)
    cold_launches: int = len(launches)
    warm: CustomRulesOutcome = evaluate_order_rules(project=project, root=tmp_path)
    warm_launches: int = len(launches) - cold_launches
    after_edit: CustomRulesOutcome = evaluate_order_rules(project=edited, root=tmp_path)
    oracle: CustomRulesOutcome = evaluate_order_rules(
        project=edited, root=tmp_path, cache_enabled=False
    )

    assert cold_launches == test_case.expected_host_runs
    assert warm_launches == 0
    assert (warm.cache_hits, warm.cache_misses) == (cold.cache_misses, 0)
    assert warm.findings == cold.findings
    assert (after_edit.cache_hits, after_edit.cache_misses) == (cold.cache_misses - 1, 1)
    assert after_edit.findings == oracle.findings


@pytest.mark.parametrize(
    "test_case",
    [
        HostFailureTestCase(
            description="earliest failure lives on a later host",
            model_count=6,
            failing_models=("orders_001", "orders_003"),
            expected_failing_model="orders_001",
        ),
        HostFailureTestCase(
            description="one failing subject",
            model_count=6,
            failing_models=("orders_005",),
            expected_failing_model="orders_005",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_rule_on_split_hosts_when_evaluating_then_single_host_error_is_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: HostFailureTestCase
) -> None:
    write_order_rules(root=tmp_path, failing=test_case.failing_models)
    project: CompiledProject = orders_project(model_count=test_case.model_count)

    _ = use_hosts(monkeypatch=monkeypatch, hosts=1)
    with pytest.raises(RulesError) as single:
        _ = evaluate_order_rules(project=project, root=tmp_path)
    monkeypatch.undo()
    _ = use_hosts(monkeypatch=monkeypatch, hosts=3)
    with pytest.raises(RulesError) as split:
        _ = evaluate_order_rules(project=project, root=tmp_path)

    assert str(split.value) == str(single.value)
    assert f"cannot inspect {test_case.expected_failing_model}" in str(split.value)


@pytest.mark.parametrize(
    "test_case",
    [
        HostPlanTestCase(
            description="project rules and whole subjects are dealt round-robin",
            plan={"XSQBRT101": None, "XSQBRT102": None, "XSQBRT103": ["models/b.sql"]},
            invocations=(
                ("XSQBRT102", ""),
                ("XSQBRT101", "models/a.sql"),
                ("XSQBRT101", "models/b.sql"),
                ("XSQBRT103", "models/b.sql"),
                ("XSQBRT101", "models/c.sql"),
            ),
            hosts=2,
            expected_plans=(
                {"XSQBRT101": ["models/b.sql"], "XSQBRT102": [""], "XSQBRT103": ["models/b.sql"]},
                {"XSQBRT101": ["models/a.sql", "models/c.sql"], "XSQBRT102": [], "XSQBRT103": []},
            ),
        ),
        HostPlanTestCase(
            description="one subject keeps the original plan",
            plan={"XSQBRT101": None},
            invocations=(("XSQBRT101", "models/a.sql"),),
            hosts=4,
            expected_plans=({"XSQBRT101": None},),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_planned_invocations_when_partitioning_then_split_is_deterministic(
    test_case: HostPlanTestCase,
) -> None:
    plans: tuple[dict[str, list[str] | None], ...] = custom_host_pool.partition_host_plan(
        plan=test_case.plan, invocations=test_case.invocations, hosts=test_case.hosts
    )

    assert plans == test_case.expected_plans


@pytest.mark.parametrize(
    "test_case",
    [
        HostCancellationTestCase(
            description="busy hosts stop at their next invocation",
            model_count=60,
            hosts=3,
            timeout_millis=120_000,
            delay_seconds=2.0,
            expected_error_fragment="cannot inspect orders_000",
            expected_max_seconds=20.0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_host_when_others_are_busy_then_they_stop_before_later_invocations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: HostCancellationTestCase
) -> None:
    write_order_rules(root=tmp_path, failing=("orders_000",), delay_seconds=test_case.delay_seconds)
    project: CompiledProject = orders_project(model_count=test_case.model_count)
    launches: list[str] = use_hosts(monkeypatch=monkeypatch, hosts=test_case.hosts)
    monkeypatch.setattr(custom_host_pool, "_HOST_TIMEOUT_MILLIS", test_case.timeout_millis)
    started: float = time.monotonic()

    with pytest.raises(RulesError) as raised:
        _ = evaluate_order_rules(project=project, root=tmp_path)

    assert time.monotonic() - started < test_case.expected_max_seconds
    assert test_case.expected_error_fragment in str(raised.value)
    assert len(launches) == test_case.hosts + 1
    assert not tuple((tmp_path / "target" / "rules-cache" / "host-inputs").iterdir())


@pytest.mark.parametrize(
    "test_case",
    [
        HostCancellationTestCase(
            description="busy hosts stop at their next invocation",
            model_count=60,
            hosts=3,
            timeout_millis=120_000,
            delay_seconds=2.0,
            expected_error_fragment="cannot inspect orders_000",
            expected_max_seconds=20.0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cancelled_hosts_when_failing_then_no_process_is_signalled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: HostCancellationTestCase
) -> None:
    write_order_rules(root=tmp_path, failing=("orders_000",), delay_seconds=test_case.delay_seconds)
    project: CompiledProject = orders_project(model_count=test_case.model_count)
    _ = use_hosts(monkeypatch=monkeypatch, hosts=test_case.hosts)
    signals: list[tuple[int, int]] = record_signals(monkeypatch=monkeypatch)

    with pytest.raises(RulesError) as raised:
        _ = evaluate_order_rules(project=project, root=tmp_path)

    assert signals == []
    assert test_case.expected_error_fragment in str(raised.value)


@pytest.mark.parametrize(
    "test_case",
    (
        HostInputsTestCase(
            description="one host waits for a slow payload",
            model_count=4,
            hosts=1,
            write_delay_seconds=1.0,
            expected_max_seconds=60.0,
        ),
        HostInputsTestCase(
            description="split hosts wait for a slow payload",
            model_count=7,
            hosts=3,
            write_delay_seconds=1.0,
            expected_max_seconds=60.0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_hosts_started_before_payload_when_payload_arrives_then_findings_are_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: HostInputsTestCase
) -> None:
    write_order_rules(root=tmp_path)
    project: CompiledProject = orders_project(model_count=test_case.model_count)
    oracle: CustomRulesOutcome = evaluate_order_rules(
        project=project, root=tmp_path, cache_enabled=False
    )
    launches: list[str] = use_hosts(monkeypatch=monkeypatch, hosts=test_case.hosts)
    delay_inputs(monkeypatch=monkeypatch, delay_seconds=test_case.write_delay_seconds)
    started: float = time.monotonic()

    delayed: CustomRulesOutcome = evaluate_order_rules(project=project, root=tmp_path)

    assert time.monotonic() - started < test_case.expected_max_seconds
    assert len(launches) == test_case.hosts
    assert delayed.findings == oracle.findings
    assert not tuple((tmp_path / "target" / "rules-cache" / "host-inputs").iterdir())


@pytest.mark.parametrize(
    "test_case",
    (
        HostInputsTestCase(
            description="one waiting host is released",
            model_count=4,
            hosts=1,
            write_delay_seconds=0.5,
            expected_max_seconds=30.0,
        ),
        HostInputsTestCase(
            description="split waiting hosts are released",
            model_count=7,
            hosts=3,
            write_delay_seconds=0.5,
            expected_max_seconds=30.0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_payload_write_failure_when_hosts_wait_then_original_error_is_raised_promptly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: HostInputsTestCase
) -> None:
    write_order_rules(root=tmp_path)
    project: CompiledProject = orders_project(model_count=test_case.model_count)
    launches: list[str] = use_hosts(monkeypatch=monkeypatch, hosts=test_case.hosts)
    fail_inputs(monkeypatch=monkeypatch, delay_seconds=test_case.write_delay_seconds)
    started: float = time.monotonic()

    with pytest.raises(OSError, match="project payload disk is full"):
        _ = evaluate_order_rules(project=project, root=tmp_path)

    assert time.monotonic() - started < test_case.expected_max_seconds
    assert len(launches) == test_case.hosts
    assert not tuple((tmp_path / "target" / "rules-cache" / "host-inputs").iterdir())


@pytest.mark.parametrize(
    "test_case",
    (
        HostInputsTestCase(
            description="one host released after its input folder vanished",
            model_count=4,
            hosts=1,
            write_delay_seconds=2.0,
            expected_max_seconds=1.0,
        ),
        HostInputsTestCase(
            description="split hosts released after their input folder vanished",
            model_count=7,
            hosts=3,
            write_delay_seconds=2.0,
            expected_max_seconds=1.0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_input_folder_removed_when_payload_write_fails_then_original_error_returns_promptly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: HostInputsTestCase
) -> None:
    write_order_rules(root=tmp_path)
    project: CompiledProject = orders_project(model_count=test_case.model_count)
    launches: list[str] = use_hosts(monkeypatch=monkeypatch, hosts=test_case.hosts)
    failures: list[float] = fail_inputs_without_directory(
        monkeypatch=monkeypatch, delay_seconds=test_case.write_delay_seconds
    )

    with pytest.raises(OSError, match="project payload disk is full"):
        _ = evaluate_order_rules(project=project, root=tmp_path)

    assert time.monotonic() - failures[0] < test_case.expected_max_seconds
    assert len(launches) == test_case.hosts
    assert not tuple((tmp_path / "target" / "rules-cache" / "host-inputs").iterdir())


@pytest.mark.parametrize(
    "test_case",
    (
        AwaitInputsTestCase(
            description="parent exited before publishing",
            reported_parent_pid=1,
            existing_files=(),
            expected_error=RulesError,
            expected_max_seconds=1.0,
        ),
        AwaitInputsTestCase(
            description="run abandoned by its parent",
            reported_parent_pid=4242,
            existing_files=("project.abandoned",),
            expected_error=HostCancelledError,
            expected_max_seconds=1.0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_waiting_host_when_parent_exits_or_run_is_abandoned_then_wait_stops_promptly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: AwaitInputsTestCase
) -> None:
    touch_files(root=tmp_path, names=test_case.existing_files)
    monkeypatch.setattr(custom_host.os, "getppid", lambda: test_case.reported_parent_pid)
    started: float = time.monotonic()

    with pytest.raises(test_case.expected_error):
        custom_host.await_inputs(
            path=tmp_path / "project.pickle",
            cancel_markers=(tmp_path / "project.abandoned",),
            parent_pid=4242,
        )

    assert time.monotonic() - started < test_case.expected_max_seconds


@pytest.mark.parametrize(
    "test_case",
    (
        AwaitPublishedInputsTestCase(
            description="payload published while the parent runs",
            reported_parent_pid=4242,
            existing_files=("project.pickle",),
            expected_max_seconds=1.0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_published_payload_when_parent_still_runs_then_wait_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: AwaitPublishedInputsTestCase
) -> None:
    touch_files(root=tmp_path, names=test_case.existing_files)
    monkeypatch.setattr(custom_host.os, "getppid", lambda: test_case.reported_parent_pid)
    started: float = time.monotonic()

    custom_host.await_inputs(
        path=tmp_path / "project.pickle",
        cancel_markers=(tmp_path / "project.abandoned",),
        parent_pid=4242,
    )

    assert time.monotonic() - started < test_case.expected_max_seconds


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
