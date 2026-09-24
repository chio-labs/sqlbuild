from __future__ import annotations

import pytest

from scripts.dupscore._helpers.clones.filters import classify_unit_change, parse_unified_diff
from scripts.dupscore._helpers.clones.tokens import build_clone_unit
from scripts.dupscore.constants import CHANGE_CHANGED, CHANGE_NEW
from scripts.dupscore.models import CloneUnit, FileChanges
from tests.unit.scripts.dupscore._helpers.clones.filters._test_types import (
    ClassifyChangeTestCase,
    ParseDiffTestCase,
)

_DIFF_TEXT: str = """\
diff --git a/src/sqlbuild/orders.py b/src/sqlbuild/orders.py
index 1111111..2222222 100644
--- a/src/sqlbuild/orders.py
+++ b/src/sqlbuild/orders.py
@@ -10,0 +11,3 @@ def summarize():
+    one
+    two
+    three
@@ -40 +43 @@ def other():
-    old
+    new
@@ -60,2 +62,0 @@ def removed():
-    gone
-    gone
diff --git a/src/sqlbuild/deleted.py b/src/sqlbuild/deleted.py
deleted file mode 100644
--- a/src/sqlbuild/deleted.py
+++ /dev/null
@@ -1,2 +0,0 @@
-x
-y
"""

_UNIT: CloneUnit = build_clone_unit(
    language="python",
    path="src/sqlbuild/orders.py",
    name="summarize",
    start_line=10,
    end_line=20,
    normalized=["$id"],
    concrete=["name"],
)


@pytest.mark.parametrize(
    "test_case",
    [
        ParseDiffTestCase(
            description="added ranges and pure deletions; deleted files are ignored",
            diff_text=_DIFF_TEXT,
            expected_changes={
                "src/sqlbuild/orders.py": FileChanges(
                    added_ranges=((11, 13), (43, 43)),
                    deletion_points=(62,),
                )
            },
        ),
        ParseDiffTestCase(
            description="empty diff has no changes",
            diff_text="",
            expected_changes={},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unified_diff_when_parsing_then_returns_added_ranges_and_deletions(
    test_case: ParseDiffTestCase,
) -> None:
    assert parse_unified_diff(test_case.diff_text) == test_case.expected_changes


@pytest.mark.parametrize(
    "test_case",
    [
        ClassifyChangeTestCase(
            description="untouched file",
            changes=None,
            expected_change=None,
        ),
        ClassifyChangeTestCase(
            description="untracked file is new",
            changes=FileChanges(whole_file=True),
            expected_change=CHANGE_NEW,
        ),
        ClassifyChangeTestCase(
            description="fully added range is new",
            changes=FileChanges(added_ranges=((5, 12), (13, 25))),
            expected_change=CHANGE_NEW,
        ),
        ClassifyChangeTestCase(
            description="partially added range is changed",
            changes=FileChanges(added_ranges=((18, 30),)),
            expected_change=CHANGE_CHANGED,
        ),
        ClassifyChangeTestCase(
            description="deletion inside the unit is changed",
            changes=FileChanges(deletion_points=(15,)),
            expected_change=CHANGE_CHANGED,
        ),
        ClassifyChangeTestCase(
            description="deletion after the last line is untouched",
            changes=FileChanges(deletion_points=(20,)),
            expected_change=None,
        ),
        ClassifyChangeTestCase(
            description="edits outside the unit are untouched",
            changes=FileChanges(added_ranges=((1, 9), (21, 40))),
            expected_change=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_file_changes_when_classifying_unit_then_returns_expected_status(
    test_case: ClassifyChangeTestCase,
) -> None:
    assert classify_unit_change(unit=_UNIT, changes=test_case.changes) == test_case.expected_change
