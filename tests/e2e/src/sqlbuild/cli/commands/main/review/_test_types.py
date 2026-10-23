"""Test types for `sqb review` E2E tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReviewOutcomeE2ETestCase:
    """One branch edit reviewed with `--json`, and the outcome the report must show."""

    description: str
    edits: dict[str, str]
    arguments: tuple[str, ...]
    expected_exit_code: int
    expected_status: str
    expected_validated: tuple[str, ...]
    expected_node_statuses: dict[str, str]
    expected_not_validated: tuple[str, ...] = ()
    expected_finding_kinds: tuple[str, ...] = ()
    expected_incomplete_nodes: tuple[str, ...] = ()
    extra_files: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewSelectErrorE2ETestCase:
    """A `--select` that cannot narrow the review, and the error it must raise."""

    description: str
    edits: dict[str, str]
    select: str
    expected_code: str
    expected_message_fragment: str


@dataclass(frozen=True)
class ReviewTextOutputE2ETestCase:
    """A human-readable review and the fragments its text and Markdown must contain."""

    description: str
    edits: dict[str, str]
    expected_stdout_fragments: tuple[str, ...]
    expected_markdown_fragments: tuple[str, ...]
    expected_exit_code: int = 0
