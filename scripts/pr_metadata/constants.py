"""Stable pull request metadata policy constants."""

import re

BRANCH_PATTERN: re.Pattern[str] = re.compile(
    r"^(feat|fix|perf|refactor|test|docs|build|ci|chore|revert)/"
    r"(?:chi-[0-9]+-)?[a-z0-9]+(?:-[a-z0-9]+)*$"
)
AUTOMATION_PATTERN: re.Pattern[str] = re.compile(
    r"^(release-please--|dependabot/|renovate/|github-actions/|blacksmith-migration-)"
)
TITLE_PATTERN: re.Pattern[str] = re.compile(
    r"^(feat|fix|perf|refactor|test|docs|build|ci|chore|revert)"
    r"(?:\([a-z0-9][a-z0-9-]*\))?!?: [^ ].+$"
)
SECTION_PATTERN: re.Pattern[str] = re.compile(r"^## (Why|Changes|Verification)\s*$", re.MULTILINE)
EXPECTED_SECTIONS: tuple[str, ...] = ("Why", "Changes", "Verification")
MAX_BODY_LENGTH: int = 2_000
