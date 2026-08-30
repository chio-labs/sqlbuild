"""Pull request metadata policy validation."""

from __future__ import annotations

import re

from scripts.pr_metadata.constants import (
    AUTOMATION_PATTERN,
    BRANCH_PATTERN,
    EXPECTED_SECTIONS,
    MAX_BODY_LENGTH,
    SECTION_PATTERN,
    TITLE_PATTERN,
)


def get_pr_metadata_errors(*, branch: str, title: str, body: str) -> tuple[str, ...]:
    """Return every pull request metadata policy violation."""
    errors: list[str] = []
    automated: bool = AUTOMATION_PATTERN.match(branch) is not None
    if not automated and BRANCH_PATTERN.fullmatch(branch) is None:
        errors.append("Branch must use <type>/<kebab-case> or <type>/chi-<number>-<kebab-case>.")
    if TITLE_PATTERN.fullmatch(title) is None:
        errors.append("PR title must follow Conventional Commits.")

    if automated:
        return tuple(errors)
    if len(body) > MAX_BODY_LENGTH:
        errors.append("PR description must not exceed 2,000 characters.")

    sections: list[re.Match[str]] = list(SECTION_PATTERN.finditer(body))
    if tuple(match.group(1) for match in sections) != EXPECTED_SECTIONS:
        errors.append(
            "PR description must contain Why, Changes, and Verification sections in that order."
        )
        return tuple(errors)

    for index, match in enumerate(sections):
        end: int = sections[index + 1].start() if index + 1 < len(sections) else len(body)
        content: str = re.sub(r"<!--.*?-->", "", body[match.end() : end], flags=re.DOTALL)
        if not content.strip():
            errors.append(f"PR description section {match.group(1)} is empty.")
    return tuple(errors)
