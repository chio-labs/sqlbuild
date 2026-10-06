"""Whole-project facts digest by content, however often resources share compiler objects."""

from pathlib import Path

import pytest

from sqlbuild.rule_engine._helpers.engine.fact_replay import _fact_value as fact_value
from sqlbuild.rule_engine._helpers.engine.fact_replay import (
    fact_outcome_digest,
    fact_value_digest,
    shared_fact_encoder,
)
from sqlbuild.rule_engine.classes.rule_context import RuleFactViews
from sqlbuild.rule_engine.constants import (
    FACT_COLUMNS_DECLARED,
    FACT_PROJECT_SOURCES,
    FACT_SQL_FOR_MODEL,
)
from sqlbuild.rule_engine.types import FactKey
from tests.unit.src.sqlbuild.rule_engine.classes.shared_fact_encoder._test_types import (
    ModelFactDigestTestCase,
    SourceDigestTestCase,
)
from tests.unit.src.sqlbuild.rule_engine.classes.shared_fact_encoder.helpers import (
    SOURCE_NAMES,
    SOURCES_CONTENTS,
    copied_file_views,
    shared_file_views,
)


@pytest.mark.parametrize(
    "test_case",
    (
        SourceDigestTestCase(
            description="unchanged declarations",
            edited_source_names=SOURCE_NAMES,
            edited_contents=SOURCES_CONTENTS,
            expected_equal=True,
        ),
        SourceDigestTestCase(
            description="shared file contents edited",
            edited_source_names=SOURCE_NAMES,
            edited_contents=SOURCES_CONTENTS + "# reviewed\n",
            expected_equal=False,
        ),
        SourceDigestTestCase(
            description="source renamed",
            edited_source_names=("raw_orders", "raw_clients"),
            edited_contents=SOURCES_CONTENTS,
            expected_equal=False,
        ),
        SourceDigestTestCase(
            description="source added",
            edited_source_names=(*SOURCE_NAMES, "raw_products"),
            edited_contents=SOURCES_CONTENTS,
            expected_equal=False,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_sources_sharing_a_file_when_digesting_then_digest_follows_content_only(
    tmp_path: Path, test_case: SourceDigestTestCase
) -> None:
    shared: RuleFactViews = shared_file_views(
        tmp_path=tmp_path, names=SOURCE_NAMES, contents=SOURCES_CONTENTS
    )
    copied: RuleFactViews = copied_file_views(
        tmp_path=tmp_path,
        names=test_case.edited_source_names,
        contents=test_case.edited_contents,
    )

    before: str = fact_outcome_digest(
        views=shared, key=(FACT_PROJECT_SOURCES,), shared=shared_fact_encoder()
    )
    after: str = fact_outcome_digest(
        views=copied, key=(FACT_PROJECT_SOURCES,), shared=shared_fact_encoder()
    )

    assert (before == after) is test_case.expected_equal


@pytest.mark.parametrize(
    "test_case",
    (
        ModelFactDigestTestCase("expanded and authored SQL", FACT_SQL_FOR_MODEL, True),
        ModelFactDigestTestCase("declared columns", FACT_COLUMNS_DECLARED, True),
    ),
    ids=lambda case: case.description,
)
def test_given_model_fact_when_digesting_with_shared_encoder_then_matches_host_observed_digest(
    tmp_path: Path, test_case: ModelFactDigestTestCase
) -> None:
    views: RuleFactViews = shared_file_views(
        tmp_path=tmp_path, names=SOURCE_NAMES, contents=SOURCES_CONTENTS
    )
    key: FactKey = (test_case.fact, views.project.models[0].path.as_posix())

    digest: str = fact_outcome_digest(views=views, key=key, shared=shared_fact_encoder())

    assert (digest == fact_value_digest(fact_value(views=views, key=key))) is (
        test_case.expected_host_digest_match
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-vv"]))
