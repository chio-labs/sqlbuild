"""Seed identity hashing tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.planner._helpers.identity.seed import build_seed_identity
from sqlbuild.spec.contracts.models import SeedCsvSettings
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    SeedIdentityCsvConfigTestCase,
    SeedIdentityTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.helpers import (
    build_seed_identity_compiled_seed,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SeedIdentityTestCase(
            description="line ending normalization preserves identity",
            seed_contents="id,name\n1,Ada\n2,Grace\n",
            comparison_contents="id,name\r\n1,Ada\r\n2,Grace\r\n",
            expected_same_identity=True,
        ),
        SeedIdentityTestCase(
            description="utf-8 bom normalization preserves identity",
            seed_contents="id,name\n1,Ada\n",
            comparison_contents="\ufeffid,name\n1,Ada\n",
            expected_same_identity=True,
        ),
        SeedIdentityTestCase(
            description="content change alters identity",
            seed_contents="id,name\n1,Ada\n",
            comparison_contents="id,name\n1,Grace\n",
            expected_same_identity=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_seed_content_when_hashing_then_identity_is_stable_and_content_sensitive(
    test_case: SeedIdentityTestCase,
    tmp_path: Path,
) -> None:
    seed_path: Path = tmp_path / "seed.csv"
    comparison_path: Path = tmp_path / "comparison.csv"
    seed_path.write_text(test_case.seed_contents, encoding="utf-8")
    comparison_path.write_text(test_case.comparison_contents, encoding="utf-8")

    seed_hash, _ = build_seed_identity(build_seed_identity_compiled_seed(seed_path))
    comparison_hash, _ = build_seed_identity(build_seed_identity_compiled_seed(comparison_path))

    assert (seed_hash == comparison_hash) is test_case.expected_same_identity


@pytest.mark.parametrize(
    "test_case",
    [
        SeedIdentityCsvConfigTestCase(
            description="csv delimiter affects identity",
            seed_contents="id|name\n1|Ada\n",
            expected_same_identity=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seed_csv_config_when_hashing_then_config_affects_identity(
    test_case: SeedIdentityCsvConfigTestCase,
    tmp_path: Path,
) -> None:
    seed_path: Path = tmp_path / "seed.csv"
    seed_path.write_text(test_case.seed_contents, encoding="utf-8")

    default_hash, _ = build_seed_identity(build_seed_identity_compiled_seed(seed_path))
    pipe_hash, _ = build_seed_identity(
        build_seed_identity_compiled_seed(seed_path, csv_settings=SeedCsvSettings(delimiter="|"))
    )

    assert (default_hash == pipe_hash) is test_case.expected_same_identity
