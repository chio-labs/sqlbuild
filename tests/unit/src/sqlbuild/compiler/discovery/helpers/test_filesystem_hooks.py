from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.exceptions import PythonNodeDiscoveryError
from sqlbuild.compiler.discovery.helpers.filesystem import discover_hook_functions
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from tests.unit.src.sqlbuild.compiler.discovery.helpers._test_types import (
    DiscoverHookFunctionsErrorTestCase,
    DiscoverHookFunctionsTestCase,
)

TEST_CASES: tuple[DiscoverHookFunctionsTestCase, ...] = (
    DiscoverHookFunctionsTestCase(
        description="discovers decorated hook functions",
        repo_files={
            "hooks/notifications.py": """
from sqlbuild.hooks import hook


@hook
def notify(ctx):
    \"\"\"Default notification hook.\"\"\"
    return None


@hook(name="notify success", description="Explicit success hook")
def notify_success(ctx):
    return None


@hook()
def plain_call(ctx):
    return None


@hook(description="Description-only hook")
def description_only(ctx):
    return None


def undecorated(ctx):
    return None
""".strip()
            + "\n",
            "hooks/nested/catalog.py": """
from sqlbuild.hooks import hook


@hook(name="catalog-publish")
def publish(ctx):
    return None
""".strip()
            + "\n",
        },
        expected_hook_names=(
            "catalog-publish",
            "description_only",
            "notify",
            "notify success",
            "plain_call",
        ),
        expected_hook_paths=(
            "hooks/nested/catalog.py",
            "hooks/notifications.py",
            "hooks/notifications.py",
            "hooks/notifications.py",
            "hooks/notifications.py",
        ),
        expected_hook_descriptions=(
            None,
            "Description-only hook",
            "Default notification hook.",
            "Explicit success hook",
            None,
        ),
        expected_function_names=(
            "publish",
            "description_only",
            "notify",
            "notify_success",
            "plain_call",
        ),
    ),
    DiscoverHookFunctionsTestCase(
        description="ignores private files and init files",
        repo_files={
            "hooks/__init__.py": """
from sqlbuild.hooks import hook


@hook
def package_hook(ctx):
    return None
""".strip()
            + "\n",
            "hooks/_private.py": """
from sqlbuild.hooks import hook


@hook
def private_hook(ctx):
    return None
""".strip()
            + "\n",
            "hooks/public.py": """
from sqlbuild.hooks import hook


@hook
def public_hook(ctx):
    return None
""".strip()
            + "\n",
        },
        expected_hook_names=("public_hook",),
        expected_hook_paths=("hooks/public.py",),
        expected_hook_descriptions=(None,),
        expected_function_names=("public_hook",),
    ),
    DiscoverHookFunctionsTestCase(
        description="does not execute hook functions during discovery",
        repo_files={
            "hooks/no_execute.py": """
from pathlib import Path
from sqlbuild.hooks import hook


@hook
def no_execute(ctx):
    Path(__file__).with_name("executed.marker").write_text("executed", encoding="utf-8")
""".strip()
            + "\n",
        },
        expected_hook_names=("no_execute",),
        expected_hook_paths=("hooks/no_execute.py",),
        expected_hook_descriptions=(None,),
        expected_function_names=("no_execute",),
        expected_marker_file_exists=False,
    ),
    DiscoverHookFunctionsTestCase(
        description="ignores imported decorated hooks",
        repo_files={
            "hooks/shared.py": """
from sqlbuild.hooks import hook


@hook(name="imported")
def imported_hook(ctx):
    return None
""".strip()
            + "\n",
            "hooks/uses_import.py": """
from sqlbuild.hooks import hook
from hooks.shared import imported_hook


@hook
def local_hook(ctx):
    return imported_hook
""".strip()
            + "\n",
        },
        expected_hook_names=("imported", "local_hook"),
        expected_hook_paths=("hooks/shared.py", "hooks/uses_import.py"),
        expected_hook_descriptions=(None, None),
        expected_function_names=("imported_hook", "local_hook"),
    ),
)


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
def test_given_hook_files_when_discovering_then_returns_decorated_hooks(
    test_case: DiscoverHookFunctionsTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    hooks: tuple[DiscoveredHookFunction, ...] = discover_hook_functions(project_dir=tmp_path)

    assert tuple(hook.name for hook in hooks) == test_case.expected_hook_names
    assert tuple(str(hook.relative_path) for hook in hooks) == test_case.expected_hook_paths
    assert tuple(hook.description for hook in hooks) == test_case.expected_hook_descriptions
    function_name_attr: str = "__name__"
    assert tuple(getattr(hook.function, function_name_attr) for hook in hooks) == (
        test_case.expected_function_names
    )
    assert all(callable(hook.function) for hook in hooks)
    assert (
        tmp_path / "hooks" / "executed.marker"
    ).is_file() is test_case.expected_marker_file_exists


ERROR_TEST_CASES: tuple[DiscoverHookFunctionsErrorTestCase, ...] = (
    DiscoverHookFunctionsErrorTestCase(
        description="duplicate hook names fail",
        repo_files={
            "hooks/first.py": """
from sqlbuild.hooks import hook


@hook(name="notify")
def notify_a(ctx):
    return None
""".strip()
            + "\n",
            "hooks/second.py": """
from sqlbuild.hooks import hook


@hook(name="notify")
def notify_b(ctx):
    return None
""".strip()
            + "\n",
        },
        expected_error_fragment="Duplicate hook name 'notify'",
    ),
    DiscoverHookFunctionsErrorTestCase(
        description="hook import failure identifies file",
        repo_files={
            "hooks/broken.py": """
from missing_package import missing_hook
""".strip()
            + "\n",
        },
        expected_error_fragment="Failed to import Python node file hooks/broken.py",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    ERROR_TEST_CASES,
    ids=[case.description for case in ERROR_TEST_CASES],
)
def test_given_invalid_hook_files_when_discovering_then_raises(
    test_case: DiscoverHookFunctionsErrorTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    with pytest.raises(PythonNodeDiscoveryError, match=test_case.expected_error_fragment):
        discover_hook_functions(project_dir=tmp_path)
