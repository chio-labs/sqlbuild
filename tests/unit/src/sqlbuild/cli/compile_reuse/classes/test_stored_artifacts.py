"""A stored artifact is trusted only while its stat identity and digest both still match."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sqlbuild.cli.compile_reuse._helpers.target_files import path_stamp
from sqlbuild.cli.compile_reuse.classes.stored_artifacts import StoredArtifacts
from sqlbuild.cli.compile_reuse.types import FileStamp
from tests.unit.src.sqlbuild.cli.compile_reuse.classes._test_types import StoredArtifactTestCase
from tests.unit.src.sqlbuild.cli.compile_reuse.classes.helpers import (
    STORED_SQL,
    artifact_digest,
    artifact_removed,
    artifact_rewritten,
    artifact_unchanged,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StoredArtifactTestCase(
            description="unchanged_same_contents",
            change=artifact_unchanged,
            written_contents=STORED_SQL,
            expected_holds=True,
        ),
        StoredArtifactTestCase(
            description="unchanged_new_contents",
            change=artifact_unchanged,
            written_contents=b"SELECT 1 AS order_id\n",
            expected_holds=False,
        ),
        StoredArtifactTestCase(
            description="rewritten_since_stored",
            change=artifact_rewritten,
            written_contents=STORED_SQL,
            expected_holds=False,
        ),
        StoredArtifactTestCase(
            description="removed_since_stored",
            change=artifact_removed,
            written_contents=STORED_SQL,
            expected_holds=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_stored_artifact_when_writing_then_trusted_only_while_stamp_and_digest_match(
    tmp_path: Path, test_case: StoredArtifactTestCase
) -> None:
    artifact: Path = tmp_path / "compiled" / "orders.sql"
    artifact.parent.mkdir()
    artifact.write_bytes(STORED_SQL)
    path: str = os.fspath(artifact)
    stamp: FileStamp | None = path_stamp(path=path)
    assert stamp is not None
    stored: StoredArtifacts = StoredArtifacts(
        stamps={path: stamp}, digests={path: artifact_digest(STORED_SQL)}
    )
    test_case.change(artifact)

    holds: bool = stored.holds(path=path, digest=artifact_digest(test_case.written_contents))

    assert holds is test_case.expected_holds


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
