from pathlib import Path

import pytest

from scripts.python_boundary.main.check import run_python_boundary_check
from tests.unit.scripts.python_boundary.main._test_types import PythonBoundaryTestCase
from tests.unit.scripts.python_boundary.main.helpers import write_boundary_project

SWALLOWED: str = (
    "from sqlbuild import _native\n"
    "\n"
    "\n"
    "def digest(text):\n"
    "    try:\n"
    "        return _native.content_digest([text])\n"
    "    except ValueError:\n"
    "        return None\n"
)
RERAISED: str = (
    "from sqlbuild._native import content_digest\n"
    "\n"
    "\n"
    "def digest(text):\n"
    "    try:\n"
    "        return content_digest([text])\n"
    "    except ValueError as error:\n"
    "        raise RuntimeError(text) from error\n"
)
CONDITIONAL: str = (
    "from sqlbuild._native import content_digest\n"
    "\n"
    "\n"
    "def digest(text, strict):\n"
    "    try:\n"
    "        return content_digest([text])\n"
    "    except ValueError:\n"
    "        if not strict:\n"
    "            return None\n"
    "        raise\n"
)
SUPPRESSED: str = (
    "import contextlib\n"
    "\n"
    "from sqlbuild.compiler.graph.main._native_project_graph import native_project_graph\n"
    "\n"
    "\n"
    "class Graph:\n"
    "    def build(self, project):\n"
    "        with contextlib.suppress(ValueError):\n"
    "            return native_project_graph(project)\n"
    "        return None\n"
)
STAYS: str = '[[stays]]\npath = "executor"\nreason = "executor"\nnote = "Runs plans."\n'
REVIEWED: str = (
    '[[handled_native_errors]]\nlocation = "compiler/keys.py::digest"\nnote = "No key."\n'
)


@pytest.mark.parametrize(
    "test_case",
    [
        PythonBoundaryTestCase(
            description="staying modules are not counted",
            source_files={"compiler/plan.py": "a = 1\nb = 2\n", "executor/run.py": "c = 3\n"},
            policy="remaining_lines = 2\n" + STAYS,
            expected_messages=("2 movable Python lines remain",),
        ),
        PythonBoundaryTestCase(
            description="names that only contain the letters native are not native calls",
            source_files={
                "compiler/plan.py": (
                    "from sqlbuild.compiler.alternatives import alternative_plan\n"
                    "\n"
                    "\n"
                    "def plan():\n"
                    "    try:\n"
                    "        return alternative_plan()\n"
                    "    except ValueError:\n"
                    "        return None\n"
                )
            },
            policy="remaining_lines = 8\n",
            expected_messages=("8 movable Python lines remain",),
        ),
        PythonBoundaryTestCase(
            description="re-raised native failures are allowed",
            source_files={"compiler/keys.py": RERAISED},
            policy="remaining_lines = 8\n",
            expected_messages=("8 movable Python lines remain",),
        ),
        PythonBoundaryTestCase(
            description="a reviewed native error handler is allowed",
            source_files={"compiler/keys.py": SWALLOWED},
            policy="remaining_lines = 8\n" + REVIEWED,
            expected_messages=("8 movable Python lines remain",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_policy_matching_source_when_checking_then_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], test_case: PythonBoundaryTestCase
) -> None:
    write_boundary_project(tmp_path, test_case)

    assert run_python_boundary_check(["--root", str(tmp_path)]) == 0
    output: str = capsys.readouterr().out
    assert all(message in output for message in test_case.expected_messages)


@pytest.mark.parametrize(
    "test_case",
    [
        PythonBoundaryTestCase(
            description="movable Python grew",
            source_files={"compiler/plan.py": "a = 1\nb = 2\nc = 3\n"},
            policy="remaining_lines = 2\n",
            expected_messages=("Movable Python grew to 3 lines (policy: 2)",),
        ),
        PythonBoundaryTestCase(
            description="movable Python shrank without lowering the baseline",
            source_files={"compiler/plan.py": "a = 1\n"},
            policy="remaining_lines = 2\n",
            expected_messages=("set remaining_lines = 1",),
        ),
        PythonBoundaryTestCase(
            description="an unreviewed native failure is swallowed",
            source_files={"compiler/keys.py": SWALLOWED},
            policy="remaining_lines = 8\n",
            expected_messages=("src/sqlbuild/compiler/keys.py:7 swallows a native failure",),
        ),
        PythonBoundaryTestCase(
            description="a handler that raises only conditionally",
            source_files={"compiler/keys.py": CONDITIONAL},
            policy="remaining_lines = 10\n",
            expected_messages=("src/sqlbuild/compiler/keys.py:7 swallows a native failure",),
        ),
        PythonBoundaryTestCase(
            description="a native wrapper call inside suppress in a method",
            source_files={"compiler/graph.py": SUPPRESSED},
            policy=(
                "remaining_lines = 10\n"
                '[[handled_native_errors]]\nlocation = "compiler/graph.py::build"\nnote = "Old."\n'
            ),
            expected_messages=(
                "src/sqlbuild/compiler/graph.py:8 swallows a native failure",
                "'compiler/graph.py::build' no longer matches any handler",
            ),
        ),
        PythonBoundaryTestCase(
            description="a staying path escapes the source root",
            source_files={"compiler/plan.py": "a = 1\n"},
            policy=(
                'remaining_lines = 0\n[[stays]]\npath = ".."\nreason = "executor"\nnote = "No."\n'
            ),
            expected_messages=("stays entry '..' must name a module under src/sqlbuild.",),
        ),
        PythonBoundaryTestCase(
            description="a reviewed handler no longer exists",
            source_files={"compiler/keys.py": RERAISED},
            policy="remaining_lines = 8\n" + REVIEWED,
            expected_messages=("'compiler/keys.py::digest' no longer matches any handler",),
        ),
        PythonBoundaryTestCase(
            description="a staying module is missing, unexplained and has an unknown reason",
            source_files={"compiler/plan.py": "a = 1\n"},
            policy=(
                'remaining_lines = 1\n[[stays]]\npath = "planner"\nreason = "too hard"\nnote = ""\n'
            ),
            expected_messages=(
                "stays entry 'planner' does not exist under src/sqlbuild.",
                "stays entry 'planner' has reason 'too hard'",
                "stays entry 'planner' needs a note explaining why it stays.",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_policy_violation_when_checking_then_fails_with_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], test_case: PythonBoundaryTestCase
) -> None:
    write_boundary_project(tmp_path, test_case)

    assert run_python_boundary_check(["--root", str(tmp_path)]) == 1
    errors: str = capsys.readouterr().err
    assert all(message in errors for message in test_case.expected_messages)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
