"""Structured runtime models for the dupscore duplication-risk advisory tool."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class FunctionFact:
    """A top-level function or method extracted from one module."""

    name: str
    qualified_name: str
    module: str
    public: bool
    lineno: int
    resolved_calls: tuple[str, ...]
    bare_attribute_calls: tuple[str, ...]
    body_tokens: frozenset[str]


@dataclass(frozen=True, slots=True)
class ClassFact:
    """A class extracted from one module, with dataclass-style field names."""

    name: str
    qualified_name: str
    module: str
    public: bool
    lineno: int
    dataclass_like: bool
    field_names: tuple[str, ...]
    methods: tuple[FunctionFact, ...]


@dataclass(frozen=True, slots=True)
class ModuleFacts:
    """All extracted facts for one Python module."""

    module: str
    relative_path: str
    functions: tuple[FunctionFact, ...]
    classes: tuple[ClassFact, ...]
    imported_modules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectFacts:
    """Extracted facts for every analyzed module of one revision."""

    modules: tuple[ModuleFacts, ...]


@dataclass(frozen=True, slots=True)
class SignalPairScore:
    """One package pair scored by a single signal."""

    package_pair: tuple[str, str]
    score: float
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SignalRanking:
    """A deterministic ranked list of package pairs for one signal."""

    signal_name: str
    entries: tuple[SignalPairScore, ...]


@dataclass(frozen=True, slots=True)
class SignalContribution:
    """One signal's rank and fused points for a combined entry."""

    signal_name: str
    rank: int
    points: float
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CombinedPairEntry:
    """One package pair in the fused ranking."""

    package_pair: tuple[str, str]
    score: float
    allowlisted: bool
    allowlist_reason: str | None
    contributions: tuple[SignalContribution, ...]


@dataclass(frozen=True, slots=True)
class DupscoreReport:
    """The complete fused duplication-risk report for one revision."""

    revision_label: str
    total_pairs: int
    entries: tuple[CombinedPairEntry, ...]


@dataclass(frozen=True, slots=True)
class PairEvidenceReport:
    """Drill-down evidence for one requested package pair."""

    package_pair: tuple[str, str]
    combined_rank: int | None
    contributions: tuple[SignalContribution, ...]


@dataclass(frozen=True, slots=True)
class ReportDelta:
    """Differences between the reports of two revisions."""

    base_label: str
    current_label: str
    entered_top: tuple[CombinedPairEntry, ...]
    left_top: tuple[CombinedPairEntry, ...]
    new_state_fanin_evidence: tuple[str, ...]
    new_same_name_evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CloneAllowlistEntry:
    """Path globs whose mutual clones are intentional, with the recorded reason."""

    paths: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class ContractExemptionEntry:
    """Methods of a contract class that classes under ``paths`` must each define themselves."""

    contract_path: str
    contract_class: str
    paths: tuple[str, ...]
    reason: str
    forbidden_owners: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class DupscoreConfig:
    """User configuration loaded from dupscore.toml."""

    persisted_state_surfaces: tuple[str, ...] = ()
    allowlisted_pairs: dict[tuple[str, str], str] = field(default_factory=dict)
    clone_allowlist: tuple[CloneAllowlistEntry, ...] = ()
    contract_exemptions: tuple[ContractExemptionEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class RustToken:
    """One lexed Rust token with its kind, spelling, and 1-based line."""

    kind: str
    text: str
    line: int


@dataclass(frozen=True, slots=True)
class CloneUnit:
    """One function-level unit with its normalised token stream."""

    language: str
    path: str
    name: str
    start_line: int
    end_line: int
    normalized: tuple[str, ...]
    concrete_key: str
    normalized_key: str


@dataclass(frozen=True, slots=True)
class ClonePair:
    """Two units whose fingerprints overlap above the similarity threshold."""

    left: int
    right: int
    similarity: float
    category: str


@dataclass(frozen=True, slots=True)
class CloneMember:
    """One unit participating in a reported clone cluster."""

    language: str
    path: str
    name: str
    start_line: int
    end_line: int
    tokens: int
    change: str | None


@dataclass(frozen=True, slots=True)
class ClonePairLink:
    """One similarity edge between two members of a cluster, by member index."""

    left: int
    right: int
    similarity: float
    category: str


@dataclass(frozen=True, slots=True)
class CloneCluster:
    """A transitive group of mutually similar units."""

    category: str
    similarity_min: float
    similarity_max: float
    duplicated_tokens: int
    members: tuple[CloneMember, ...]
    links: tuple[ClonePairLink, ...]


@dataclass(frozen=True, slots=True)
class CloneOptions:
    """Detection and reporting options for the clones mode."""

    languages: tuple[str, ...]
    include_tests: bool
    min_tokens: int
    min_similarity: float
    path_globs: tuple[str, ...]
    since: str | None


@dataclass(frozen=True, slots=True)
class CloneReport:
    """Every reported clone cluster for the worktree."""

    since: str | None
    unit_counts: dict[str, int]
    allowlisted_pairs: int
    contract_exempt_members: int
    clusters: tuple[CloneCluster, ...]


@dataclass(frozen=True, slots=True)
class FileChanges:
    """Lines of one file added or changed since a base revision."""

    added_ranges: tuple[tuple[int, int], ...] = ()
    deletion_points: tuple[int, ...] = ()
    whole_file: bool = False


@dataclass(frozen=True, slots=True)
class RustFileUnits:
    """Units found in one Rust file plus the test-only module files it declares."""

    units: tuple[CloneUnit, ...]
    test_module_prefixes: tuple[str, ...]
