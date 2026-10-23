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


@dataclass(frozen=True)
class ReviewIncrementalStartE2ETestCase:
    """A review that builds an incremental model, and how the report says it started."""

    description: str
    arguments: tuple[str, ...]
    expected_starts: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ReviewSelectionE2ETestCase:
    """A `--select` inside the changed set, and what the review validates."""

    description: str
    select: str
    expected_validated: tuple[str, ...]
    expected_not_validated_member: str


@dataclass(frozen=True)
class ReviewSelectedAncestorE2ETestCase:
    """A `--select` below a changed model, and the findings the added ancestor must show."""

    description: str
    edits: dict[str, str]
    select: str
    expected_exit_code: int
    expected_validated: tuple[str, ...]
    expected_added: tuple[tuple[str, str], ...]
    expected_finding_nodes: frozenset[str]


@dataclass(frozen=True)
class ReviewDatabaseE2ETestCase:
    """A changed model with its own database, and the review database it must build in."""

    description: str
    edits: dict[str, str]
    arguments: tuple[str, ...]
    expected_exit_code: int
    expected_database: str


@dataclass(frozen=True)
class ReviewMarkdownFailureE2ETestCase:
    """A `--markdown` path the review cannot write, and the outcome it must still report."""

    description: str
    edits: dict[str, str]
    expected_stdout_fragment: str
    expected_code: str
    expected_status: str
    expected_finding_kinds: frozenset[str]


@dataclass(frozen=True)
class ReviewUsageErrorE2ETestCase:
    """Arguments `sqb review` rejects, and the setup failure they must exit with."""

    description: str
    arguments: tuple[str, ...]
    expected_message_fragment: str


@dataclass(frozen=True)
class ReviewSetupFailureE2ETestCase:
    """A review that fails before creating its schema, and the error it reports."""

    description: str
    edits: dict[str, str]
    arguments: tuple[str, ...]
    expected_code: str
    expected_message_fragment: str
    expected_node_statuses: frozenset[str]
    extra_files: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewDryRunE2ETestCase:
    """A dry run, and the plan it reports without touching the warehouse."""

    description: str
    expected_status: str
    expected_validated: tuple[str, ...]
    expected_node_statuses: frozenset[str]
    edits: dict[str, str] = field(default_factory=dict)
    expected_hooks: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewCleanupFailureE2ETestCase:
    """A review whose schema drop fails, and the leftover the janitor later removes."""

    description: str
    expired_schema: str
    expected_exit_code: int
