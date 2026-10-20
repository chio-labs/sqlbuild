"""Third-party library logs during a command: what the console shows and what Recall keeps."""

import subprocess
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.recall._test_types import ThirdPartyLogTestCase
from tests.integration.src.sqlbuild.cli.recall.helpers import recall_rows, run, write_project

VENDOR_TASK: str = (
    '"""A task whose client library logs while it runs."""\n\n'
    "import logging\n\n"
    "from sqlbuild.tasks import task\n\n\n"
    "@task()\n"
    "def sync_orders(ctx):\n"
    '    """Log like a client library: progress, then a recovered failure."""\n\n'
    '    logger = logging.getLogger("vendor.client")\n'
    '    logger.info("connecting to the orders service")\n'
    "    try:\n"
    '        raise RuntimeError("token expired")\n'
    "    except RuntimeError:\n"
    '        logger.warning("token refresh failed", exc_info=True)\n'
    "    return ctx.result()\n"
)
TRACEBACK: str = "Traceback (most recent call last):"


@pytest.mark.parametrize(
    "test_case",
    (
        ThirdPartyLogTestCase(
            description="normal output hides INFO and shows the warning as one line",
            build_arguments=("build",),
            expected_present=("[warning] vendor.client token refresh failed",),
            expected_absent=("connecting to the orders service", TRACEBACK, "token expired"),
        ),
        ThirdPartyLogTestCase(
            description="debug output shows every record with its traceback",
            build_arguments=("--debug", "build"),
            expected_present=(
                "[info] vendor.client connecting to the orders service",
                "[warning] vendor.client token refresh failed",
                TRACEBACK,
                "RuntimeError: token expired",
            ),
            expected_absent=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_library_logs_during_build_when_running_then_console_is_quiet_and_recall_keeps_all(
    test_case: ThirdPartyLogTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "orders_shop")
    (project_dir / "python" / "tasks" / "emit.py").write_text(VENDOR_TASK, encoding="utf-8")

    built: subprocess.CompletedProcess[bytes] = run(project_dir, *test_case.build_arguments)

    stderr: str = built.stderr.decode(errors="replace")
    assert built.returncode == 0, stderr
    assert stderr.count("[warning] vendor.client token refresh failed") == 1, stderr
    fragment: str
    for fragment in test_case.expected_present:
        assert fragment in stderr, stderr
    for fragment in test_case.expected_absent:
        assert fragment not in stderr, stderr
    rows: list[list[object]] = recall_rows(
        project_dir,
        "SELECT severity, message FROM diagnostics "
        "WHERE logger = 'vendor.client' ORDER BY occurred_at",
    )
    assert [row[0] for row in rows] == ["info", "warning"]
    assert rows[0][1] == "connecting to the orders service"
    warning: str = str(rows[1][1])
    assert warning.startswith("token refresh failed\n" + TRACEBACK), warning
    assert "RuntimeError: token expired" in warning
