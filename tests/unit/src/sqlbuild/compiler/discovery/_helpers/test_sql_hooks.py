from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.compiler.discovery._helpers.filesystem.core import discover_sql_hook_files
from sqlbuild.compiler.discovery._helpers.sql.hooks import parse_sql_hook_file
from sqlbuild.compiler.discovery.exceptions import SqlHookParseError
from sqlbuild.compiler.discovery.models import DiscoveredSqlHookFile
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    DiscoverSqlHooksTestCase,
    ParseSqlHookErrorTestCase,
    ParseSqlHookTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ParseSqlHookTestCase(
            description="parses hook description and SQL body",
            contents=(
                "HOOK (description: \"Grant access\");\n\nGRANT SELECT ON @relation TO @'role'\n"
            ),
            expected_name="grant_access",
            expected_description="Grant access",
            expected_sql_body="GRANT SELECT ON @relation TO @'role'",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_hook_header_and_sql_when_parsing_then_returns_named_resource(
    test_case: ParseSqlHookTestCase,
) -> None:
    hook: DiscoveredSqlHookFile = parse_sql_hook_file(
        contents=test_case.contents,
        file_path=Path("/project/hooks/sql/grant_access.sql"),
        relative_path=Path("hooks/sql/grant_access.sql"),
    )

    assert hook.name == test_case.expected_name
    assert hook.description == test_case.expected_description
    assert hook.sql_body == test_case.expected_sql_body
    assert hook.relative_path == Path("hooks/sql/grant_access.sql")


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoverSqlHooksTestCase(
            description="discovers nested public SQL hooks only",
            repo_files={
                "hooks/sql/admin/grant_access.sql": "HOOK ();\n\nSELECT 1\n",
                "hooks/sql/_private.sql": "not a hook\n",
                "hooks/python/not_sql.sql": "not a hook\n",
            },
            expected_names=("grant_access",),
            expected_paths=("hooks/sql/admin/grant_access.sql",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_nested_sql_hook_files_when_discovering_then_names_come_from_stems(
    test_case: DiscoverSqlHooksTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    hooks: tuple[DiscoveredSqlHookFile, ...] = discover_sql_hook_files(project_dir=tmp_path)

    assert tuple(hook.name for hook in hooks) == test_case.expected_names
    assert tuple(hook.relative_path.as_posix() for hook in hooks) == test_case.expected_paths


@pytest.mark.parametrize(
    "test_case",
    [
        ParseSqlHookErrorTestCase(
            description="rejects multiple hook blocks",
            contents="HOOK ();\nSELECT 1\n\nHOOK ();\nSELECT 2\n",
            expected_error_fragment="exactly one HOOK",
        ),
        ParseSqlHookErrorTestCase(
            description="rejects unsupported hook header key",
            contents='HOOK (name: "override");\nSELECT 1\n',
            expected_error_fragment="unsupported keys: name",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_sql_hook_when_parsing_then_raises(
    test_case: ParseSqlHookErrorTestCase,
) -> None:
    with pytest.raises(SqlHookParseError, match=test_case.expected_error_fragment):
        parse_sql_hook_file(
            contents=test_case.contents,
            file_path=Path("hooks/sql/invalid.sql"),
            relative_path=Path("hooks/sql/invalid.sql"),
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
