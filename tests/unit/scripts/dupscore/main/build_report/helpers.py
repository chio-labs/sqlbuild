from __future__ import annotations

import subprocess
from pathlib import Path

_TWIN_BODY: str = (
    "def resolve_target_relation(name: str) -> str:\n    return name.strip().lower()\n"
)
_LEAVES: str = (
    "def leaf_one() -> int:\n    return 1\n\n"
    "def leaf_two() -> int:\n    return 2\n\n"
    "def leaf_three() -> int:\n    return 3\n\n"
    "def leaf_four() -> int:\n    return 4\n\n"
    "def leaf_five() -> int:\n    return 5\n"
)
_LEAF_IMPORT: str = (
    "from sqlbuild.alpha.primitives.leaves import ("
    "leaf_one, leaf_two, leaf_three, leaf_four, leaf_five)\n"
)
_LEAF_SUM: str = "leaf_one() + leaf_two() + leaf_three() + leaf_four() + leaf_five()"
_PLANNER_ENTRY: str = (
    _LEAF_IMPORT
    + "from sqlbuild.alpha.planner.middle import plan_middle\n"
    + "\n"
    + "def run_plan() -> int:\n"
    + f"    return {_LEAF_SUM} + plan_middle()\n"
)
_EXECUTOR_ENTRY: str = (
    _LEAF_IMPORT
    + "from sqlbuild.alpha.executor.middle import build_middle\n"
    + "\n"
    + "def run_build() -> int:\n"
    + f"    return {_LEAF_SUM} + build_middle()\n"
)
_PLANNER_MIDDLE: str = (
    "from sqlbuild.alpha.primitives.leaves import leaf_one\n"
    "\n"
    "def plan_middle() -> int:\n"
    "    return leaf_one()\n"
)
_EXECUTOR_MIDDLE: str = (
    "from sqlbuild.alpha.primitives.leaves import leaf_two\n"
    "\n"
    "def build_middle() -> int:\n"
    "    return leaf_two()\n"
)
_STATE_CLASS: str = (
    "class StateBackend:\n"
    "    def get_model_refs(self) -> list[str]:\n"
    "        return []\n"
    "\n"
    "    def get_seed_refs(self) -> list[str]:\n"
    "        return []\n"
)
_PLANNER_STATE_READER: str = (
    "def read_plan_state(backend: object) -> None:\n"
    "    backend.get_model_refs()\n"
    "    backend.get_seed_refs()\n"
)
_EXECUTOR_STATE_READER: str = (
    "def read_build_state(backend: object) -> None:\n"
    "    backend.get_model_refs()\n"
    "    backend.get_seed_refs()\n"
)

BASE_PROJECT_FILES: dict[str, str] = {
    "src/sqlbuild/alpha/primitives/leaves.py": _LEAVES,
    "src/sqlbuild/alpha/planner/plan.py": _PLANNER_ENTRY,
    "src/sqlbuild/alpha/planner/middle.py": _PLANNER_MIDDLE,
    "src/sqlbuild/alpha/executor/build.py": _EXECUTOR_ENTRY,
    "src/sqlbuild/alpha/executor/middle.py": _EXECUTOR_MIDDLE,
    "src/sqlbuild/alpha/state/backend.py": _STATE_CLASS,
    "src/sqlbuild/alpha/planner/bound_state.py": _PLANNER_STATE_READER,
    "src/sqlbuild/alpha/executor/bound_state.py": _EXECUTOR_STATE_READER,
}

TWIN_PROJECT_FILES: dict[str, str] = {
    "src/sqlbuild/alpha/planner/targets.py": _TWIN_BODY,
    "src/sqlbuild/alpha/executor/rewrite.py": _TWIN_BODY,
}


def write_project_files(*, repo_root: Path, files: dict[str, str]) -> None:
    for relative, contents in files.items():
        target: Path = repo_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")


def run_git(*, repo_root: Path, arguments: list[str]) -> str:
    completed: subprocess.CompletedProcess[str] = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def initialize_repo(repo_root: Path) -> None:
    _ = run_git(repo_root=repo_root, arguments=["init", "--quiet"])
    _ = run_git(repo_root=repo_root, arguments=["config", "user.email", "dupscore@test.local"])
    _ = run_git(repo_root=repo_root, arguments=["config", "user.name", "Dupscore Test"])


def commit_all(*, repo_root: Path, message: str) -> str:
    _ = run_git(repo_root=repo_root, arguments=["add", "--all"])
    _ = run_git(repo_root=repo_root, arguments=["commit", "--quiet", "--message", message])
    return run_git(repo_root=repo_root, arguments=["rev-parse", "HEAD"])
