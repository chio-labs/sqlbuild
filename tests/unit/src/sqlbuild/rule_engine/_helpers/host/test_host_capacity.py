"""Host capacity honours container CPU quotas from cgroup v1 and v2."""

import os
from pathlib import Path

import pytest

from sqlbuild.rule_engine._helpers.host import custom_host_pool
from sqlbuild.rule_engine._helpers.host.host_capacity import available_cores
from tests.unit.src.sqlbuild.rule_engine._helpers.host._test_types import HostCapacityTestCase
from tests.unit.src.sqlbuild.rule_engine._helpers.host.helpers import write_cgroup_files

_NODE_CPUS: int = 64


@pytest.mark.parametrize(
    "test_case",
    [
        HostCapacityTestCase(
            description="cgroup v2 quota on the process cgroup",
            proc_cgroup="0::/kubepods/orders\n",
            files={"kubepods/orders/cpu.max": "400000 100000\n"},
            expected_cores=4,
        ),
        HostCapacityTestCase(
            description="cgroup v2 fractional quota rounds up",
            proc_cgroup="0::/kubepods/orders\n",
            files={"kubepods/orders/cpu.max": "150000 100000\n"},
            expected_cores=2,
        ),
        HostCapacityTestCase(
            description="cgroup v2 ancestor quota is tighter",
            proc_cgroup="0::/kubepods/orders\n",
            files={
                "kubepods/cpu.max": "200000 100000\n",
                "kubepods/orders/cpu.max": "800000 100000\n",
            },
            expected_cores=2,
        ),
        HostCapacityTestCase(
            description="cgroup v2 without a quota",
            proc_cgroup="0::/\n",
            files={"cpu.max": "max 100000\n"},
            expected_cores=_NODE_CPUS,
        ),
        HostCapacityTestCase(
            description="cgroup v1 CFS quota",
            proc_cgroup="4:cpu,cpuacct:/docker/orders\n",
            files={
                "cpu,cpuacct/docker/orders/cpu.cfs_quota_us": "300000\n",
                "cpu,cpuacct/docker/orders/cpu.cfs_period_us": "100000\n",
            },
            expected_cores=3,
        ),
        HostCapacityTestCase(
            description="cgroup v1 unlimited CFS quota",
            proc_cgroup="4:cpu,cpuacct:/\n",
            files={
                "cpu,cpuacct/cpu.cfs_quota_us": "-1\n",
                "cpu,cpuacct/cpu.cfs_period_us": "100000\n",
            },
            expected_cores=_NODE_CPUS,
        ),
        HostCapacityTestCase(
            description="no cgroup files", proc_cgroup="", files={}, expected_cores=_NODE_CPUS
        ),
        HostCapacityTestCase(
            description="non-UTF-8 cgroup v2 quota is ignored",
            proc_cgroup="0::/kubepods/orders\n",
            files={"kubepods/orders/cpu.max": "\udcff\udcfe 100000\n"},
            expected_cores=_NODE_CPUS,
        ),
        HostCapacityTestCase(
            description="non-UTF-8 process cgroup is ignored",
            proc_cgroup="0::/kubepods/\udcff\n",
            files={"kubepods/cpu.max": "200000 100000\n"},
            expected_cores=_NODE_CPUS,
        ),
        HostCapacityTestCase(
            description="non-UTF-8 cgroup v1 quota is ignored",
            proc_cgroup="4:cpu,cpuacct:/\n",
            files={
                "cpu,cpuacct/cpu.cfs_quota_us": "\udcff\n",
                "cpu,cpuacct/cpu.cfs_period_us": "100000\n",
            },
            expected_cores=_NODE_CPUS,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cgroup_quota_when_counting_cores_then_quota_caps_process_cpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: HostCapacityTestCase
) -> None:
    proc_cgroup: Path = write_cgroup_files(
        root=tmp_path, proc_cgroup=test_case.proc_cgroup, files=test_case.files
    )
    monkeypatch.setattr(os, "process_cpu_count", lambda: _NODE_CPUS, raising=False)

    cores: int = available_cores(cgroup_root=tmp_path / "cgroup", proc_cgroup=proc_cgroup)

    assert cores == test_case.expected_cores


@pytest.mark.parametrize(
    "test_case",
    [
        HostCapacityTestCase(
            description="hosts are capped on a large node",
            proc_cgroup="",
            files={},
            expected_cores=8,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_many_cores_when_partitioning_then_at_most_eight_hosts_start(
    monkeypatch: pytest.MonkeyPatch, test_case: HostCapacityTestCase
) -> None:
    monkeypatch.setattr(custom_host_pool, "available_cores", lambda: _NODE_CPUS)
    invocations: tuple[tuple[str, str], ...] = tuple(
        ("XSQBRT101", f"models/orders_{index:04d}.sql") for index in range(10_000)
    )

    plans: tuple[dict[str, list[str] | None], ...] = custom_host_pool.partition_host_plan(
        plan={"XSQBRT101": None},
        invocations=invocations,
        hosts=custom_host_pool.host_count(len(invocations)),
    )

    assert len(plans) == test_case.expected_cores


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
