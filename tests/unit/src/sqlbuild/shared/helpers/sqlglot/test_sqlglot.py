from __future__ import annotations

import pytest

from sqlbuild.shared.helpers import sqlglot
from tests.unit.src.sqlbuild.shared.helpers.sqlglot._test_types import (
    SqlglotImportTestCase,
)
from tests.unit.src.sqlbuild.shared.helpers.sqlglot.helpers import raise_import_error_for


@pytest.mark.parametrize(
    "test_case",
    [
        SqlglotImportTestCase(
            description="reports unavailable when SQLGlot import fails",
            missing_module_name="sqlglot",
            expected_available=False,
        )
    ],
    ids=["reports unavailable when SQLGlot import fails"],
)
def test_given_missing_sqlglot_when_checking_availability_then_returns_false(
    test_case: SqlglotImportTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sqlglot,
        "import_module",
        raise_import_error_for(test_case.missing_module_name),
    )

    assert sqlglot.is_sqlglot_available() is test_case.expected_available
    assert sqlglot.import_sqlglot() is None
