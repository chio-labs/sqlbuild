from dataclasses import dataclass


@dataclass(frozen=True)
class FormatCodedErrorTestCase:
    description: str
    code: str
    message: str
    help: str | None
    use_color: bool
    expected_rendered: str


@dataclass(frozen=True)
class CliStyleTestCase:
    description: str
    use_color: bool
    expected_title: str
    expected_section: str
    expected_label: str
    expected_value: str
    expected_accent: str
    expected_plan_section: str
    expected_success: str
    expected_success_strong: str
    expected_warning: str
    expected_warning_strong: str
    expected_error: str
    expected_error_strong: str
    expected_error_muted: str
    expected_log_label: str
    expected_status_ok: str
    expected_status_error: str
    expected_status_skip: str
    expected_dbt_section: str
    expected_dbt_object_name: str


@dataclass(frozen=True)
class CliDocumentTestCase:
    description: str
    use_color: bool
    expected_rendered: str


@dataclass(frozen=True)
class ProgressSpinnersDisabledTestCase:
    description: str
    env_value: str | None
    expected_disabled: bool


@dataclass(frozen=True)
class SummaryFooterTestCase:
    description: str
    counts: tuple[tuple[str, int], ...]
    elapsed: str | None
    expected_no_color: str
    expected_color_fragments: tuple[str, ...]


@dataclass(frozen=True)
class PrephaseCauseAnnotationTestCase:
    description: str
    caused_by_names: tuple[str, ...]
    expected_annotation: str


@dataclass(frozen=True)
class PrephaseCloneItemRowTestCase:
    description: str
    action: str
    status: str
    expected_label: str
    expected_status: str


@dataclass(frozen=True)
class RelationLookupTestCase:
    description: str
    warehouse_relations: tuple[tuple[str | None, str, bool | None], ...]
    locations: tuple[tuple[str | None, str | None, str], ...]
    probe_schema: str | None
    probe_name: str
    expected_exists: bool
    expected_is_transient: bool
    expected_list_relations_calls: int
    expected_queried_relation_calls: tuple[tuple[str | None, tuple[str, ...]], ...]
    probe_database: str | None = None


@dataclass(frozen=True)
class LocalNodePlanningTestCase:
    description: str
    fingerprint_exists: bool
    relation_exists: bool
    full_refresh: bool
    local_hash: str | None
    previous_hash: str | None
    expected_action: str
    expected_reason: str


@dataclass(frozen=True)
class InvertEdgesTestCase:
    description: str
    edges: dict[str, tuple[str, ...]]
    expected_edges: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class TransitiveClosureTestCase:
    description: str
    edges: dict[str, tuple[str, ...]]
    start: str
    max_depth: int | None
    expected_nodes: frozenset[str]


@dataclass(frozen=True)
class PathNodesTestCase:
    description: str
    downstream: dict[str, tuple[str, ...]]
    start: str
    end: str
    expected_nodes: frozenset[str] | None


@dataclass(frozen=True)
class CloneBoundaryTestCase:
    description: str
    upstream: dict[str, tuple[str, ...]]
    selected: frozenset[str]
    clonable_nodes: frozenset[str]
    view_nodes: frozenset[str]
    expected_boundary_nodes: frozenset[str]
    expected_view_chain_nodes: frozenset[str]


@dataclass(frozen=True)
class SelectorExpansionTestCase:
    description: str
    raw: str
    expected_core: str
    expected_upstream: bool
    expected_downstream: bool


@dataclass(frozen=True)
class SelectorExpansionErrorTestCase:
    description: str
    raw: str
    expected_error_type: type[Exception]
