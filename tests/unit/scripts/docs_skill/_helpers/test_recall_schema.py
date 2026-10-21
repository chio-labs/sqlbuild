import pytest

from scripts.docs_skill._helpers.recall_schema import with_recall_views
from scripts.docs_skill.constants import SCHEMA_SECTION_END, SCHEMA_SECTION_START
from tests.unit.scripts.docs_skill._helpers._test_types import RecallViewsSectionTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        RecallViewsSectionTestCase(
            description="an empty section is filled",
            guide=f"# Guide\n\n{SCHEMA_SECTION_START}\n{SCHEMA_SECTION_END}\n",
            views="orders (view)\n  order_id TEXT\n",
            expected_guide=(
                f"# Guide\n\n{SCHEMA_SECTION_START}\n\n```text\norders (view)\n  order_id TEXT\n"
                f"```\n\n{SCHEMA_SECTION_END}\n"
            ),
        ),
        RecallViewsSectionTestCase(
            description="a stale section is replaced and the text around it kept",
            guide=(
                f"intro\n{SCHEMA_SECTION_START}\n\n```text\nold (view)\n```\n\n"
                f"{SCHEMA_SECTION_END}\noutro\n"
            ),
            views="customers (view)\n",
            expected_guide=(
                f"intro\n{SCHEMA_SECTION_START}\n\n```text\ncustomers (view)\n```\n\n"
                f"{SCHEMA_SECTION_END}\noutro\n"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_guide_when_the_views_section_is_rendered_then_only_that_section_changes(
    test_case: RecallViewsSectionTestCase,
) -> None:
    rendered: str = with_recall_views(guide=test_case.guide, views=test_case.views)

    assert rendered == test_case.expected_guide
    assert with_recall_views(guide=rendered, views=test_case.views) == test_case.expected_guide
