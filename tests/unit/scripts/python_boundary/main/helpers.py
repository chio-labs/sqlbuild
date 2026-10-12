from pathlib import Path

from tests.unit.scripts.python_boundary.main._test_types import PythonBoundaryTestCase


def write_boundary_project(root: Path, test_case: PythonBoundaryTestCase) -> None:
    """Write a source tree under src/sqlbuild and its python-boundary.toml."""
    for relative_path, contents in test_case.source_files.items():
        path: Path = root / "src" / "sqlbuild" / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    (root / "python-boundary.toml").write_text(test_case.policy, encoding="utf-8")
