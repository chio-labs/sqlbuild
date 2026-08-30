import pytest

from scripts.pr_metadata._helpers.validation import get_pr_metadata_errors
from tests.unit.scripts.pr_metadata._helpers._test_types import PrMetadataValidationTestCase

VALID_BODY: str = "## Why\nReason\n\n## Changes\nChange\n\n## Verification\nTested\n"


@pytest.mark.parametrize(
    "test_case",
    [
        PrMetadataValidationTestCase(
            description="valid issue branch and complete body",
            branch="feat/chi-137-named-connections",
            title="feat: add named connections",
            body=VALID_BODY,
            expected_errors=(),
        ),
        PrMetadataValidationTestCase(
            description="body exactly at maximum length",
            branch="ci/local-pr-check",
            title="ci: add local PR check",
            body=VALID_BODY + "x" * (2_000 - len(VALID_BODY)),
            expected_errors=(),
        ),
        PrMetadataValidationTestCase(
            description="automation branch skips human body requirements",
            branch="dependabot/pip/ruff-1.0",
            title="chore(deps): update ruff",
            body="",
            expected_errors=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_valid_metadata_when_validating_then_returns_no_errors(
    test_case: PrMetadataValidationTestCase,
) -> None:
    errors: tuple[str, ...] = get_pr_metadata_errors(
        branch=test_case.branch,
        title=test_case.title,
        body=test_case.body,
    )

    assert errors == test_case.expected_errors


@pytest.mark.parametrize(
    "test_case",
    [
        PrMetadataValidationTestCase(
            description="invalid branch",
            branch="kvlonge/chi-137-named-connections",
            title="feat: add named connections",
            body=VALID_BODY,
            expected_errors=(
                "Branch must use <type>/<kebab-case> or <type>/chi-<number>-<kebab-case>.",
            ),
        ),
        PrMetadataValidationTestCase(
            description="non-conventional title",
            branch="feat/named-connections",
            title="Add named connections",
            body=VALID_BODY,
            expected_errors=("PR title must follow Conventional Commits.",),
        ),
        PrMetadataValidationTestCase(
            description="body exceeds maximum length",
            branch="feat/named-connections",
            title="feat: add named connections",
            body=VALID_BODY + "x" * (2_001 - len(VALID_BODY)),
            expected_errors=("PR description must not exceed 2,000 characters.",),
        ),
        PrMetadataValidationTestCase(
            description="sections are out of order",
            branch="feat/named-connections",
            title="feat: add named connections",
            body="## Changes\nChange\n## Why\nReason\n## Verification\nTested\n",
            expected_errors=(
                "PR description must contain Why, Changes, and Verification sections in that order.",
            ),
        ),
        PrMetadataValidationTestCase(
            description="comment-only section is empty",
            branch="feat/named-connections",
            title="feat: add named connections",
            body=("## Why\n<!-- reason -->\n\n## Changes\nChange\n\n## Verification\nTested\n"),
            expected_errors=("PR description section Why is empty.",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_metadata_when_validating_then_returns_policy_errors(
    test_case: PrMetadataValidationTestCase,
) -> None:
    errors: tuple[str, ...] = get_pr_metadata_errors(
        branch=test_case.branch,
        title=test_case.title,
        body=test_case.body,
    )

    assert errors == test_case.expected_errors


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
