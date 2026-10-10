"""Private SQLBuild native engine bindings."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypedDict

from sqlbuild.compiler.sql_test_glue.models import (
    NativeSqlTestAssemblyRequest,
    NativeSqlTestChainRequest,
    NativeSqlTestPlanningRequest,
)
from sqlbuild.compiler.sql_test_glue.types import NativeSqlTestAssemblyRow, NativeSqlTestPlanRow

BUILD_IDENTITY: str

class LintPreparationRequest(TypedDict):
    expanded: str
    before_expansion: str
    prior_sites: list[int]
    dialect: str

class ParsedRulesRequest:
    """Decoded built-in rules request held natively until it is evaluated once."""

def analyze_column_references_json(request_json: str) -> str: ...
def catalogue_json() -> str: ...
def evaluate_json(request_json: str) -> str: ...
def parse_rules_parts(
    request_json: bytes, model_jsons: list[bytes], model_digests: list[str]
) -> ParsedRulesRequest: ...
def evaluate_parsed_rules(parsed: ParsedRulesRequest) -> str: ...
def finalize_rule_findings_json(request_json: str) -> str: ...
def run_custom_host_json(spec_json: str) -> str: ...
def format_sql_json(request_json: str) -> str: ...
def format_sql_batch_json(request_json: str) -> str: ...
def query_fingerprint(sql: str, dialect: str) -> str: ...
def lint_sql_json(request_json: str) -> str: ...
def lint_sql_batch_json(request_json: str) -> str: ...
def prepare_lint_sql(
    request: LintPreparationRequest,
) -> tuple[str, list[tuple[str, int, int, int, int, str]], list[str]] | None: ...
def prepare_lint_sql_batch(
    requests: list[LintPreparationRequest],
) -> list[tuple[bool, tuple[str, list[tuple[str, int, int, int, int, str]], list[str]] | None]]: ...
def lint_backtick_identifiers(dialect: str) -> bool: ...
def load_config_json(project_dir: str) -> str: ...
def selected_codes_json(request_json: str) -> str: ...
def render_owned_skill(content: str, input_fingerprint: str) -> str: ...
def skill_freshness(content: str | None, input_fingerprint: str) -> str: ...
def match_model_headers(contents: list[str]) -> list[tuple[int, int, int] | None]: ...
def parse_model_headers(
    headers: list[str],
) -> list[tuple[dict[str, object] | None, list[tuple[str, int, int]] | None, str | None]]: ...
def tokenize_model_header(header: str) -> list[tuple[int, str, int]]: ...
def native_text_supported(python_version: tuple[int, int], unicode_version: str) -> bool: ...

class NativeProjectTree:
    def __init__(self, project_dir: str) -> None: ...
    def listings(self) -> list[tuple[str, list[tuple[str, bool, bool]]]]: ...

def discover_model_files(
    request: dict[str, object], tree: NativeProjectTree
) -> list[tuple[str, tuple[object, ...]]] | tuple[object, ...]: ...
def discover_sql_test_files(
    request: dict[str, object], tree: NativeProjectTree
) -> list[tuple[str, tuple[object, ...]]] | tuple[object, ...]: ...
def discover_scenario_files(
    request: dict[str, object], tree: NativeProjectTree
) -> list[tuple[str, tuple[object, ...]]] | tuple[object, ...]: ...
def load_yaml_files(
    request: dict[str, object], relative_paths: list[str], tree: NativeProjectTree
) -> list[tuple[object, ...]] | tuple[object, ...]: ...
def load_yaml_document(file_path: str, text: str, kind: str) -> tuple[object, ...]: ...

class NativeDiscoverySession:
    def __init__(self, request: dict[str, object]) -> None: ...
    def collection(
        self, kind: str, tree: NativeProjectTree, isolate_kind: bool = False
    ) -> (
        list[
            tuple[
                str, tuple[str, str, str | None, str | None, str | None] | None, tuple[object, ...]
            ]
        ]
        | tuple[object, ...]
    ): ...

def parse_declaration_contents(
    request: dict[str, object], names: tuple[str, str], contents: str
) -> tuple[object, ...]: ...
def discover_declaration_layout(
    tree: NativeProjectTree, kind: str | None = None
) -> tuple[tuple[object, ...], tuple[object, ...]] | tuple[object, ...]: ...
def parse_model_contents(request: dict[str, object], contents: str) -> tuple[object, ...]: ...
def parse_sql_test_contents(request: dict[str, object], contents: str) -> tuple[object, ...]: ...
def parse_scenario_contents(request: dict[str, object], contents: str) -> tuple[object, ...]: ...

class NativeDeclarationContexts:
    def __init__(
        self,
        positions: list[tuple[object, ...]],
        table: tuple[list[int], dict[str, list[int]], dict[str, list[int]]],
        classes: dict[str, object],
        lookup: dict[str, object],
    ) -> None: ...
    def context(self, matches: Sequence[Any], consumer: object) -> Any: ...

class NativeScopeIndex:
    def records(
        self,
    ) -> tuple[
        list[str],
        list[tuple[str, str, str, str | None, str | None]],
        list[int],
        list[int],
        list[tuple[int, int]],
        list[tuple[str, str, str | None, int | None, int | None, int | None, int | None]],
        bool,
    ]: ...
    def grant(
        self, facts: list[tuple[str, str, list[str], list[str], list[str]]]
    ) -> list[tuple[str, str, int, str | int, str]] | None: ...
    def lookup(
        self,
    ) -> (
        tuple[
            list[int],
            list[int],
            list[int],
            list[int],
            tuple[
                tuple[list[list[int]], bool],
                tuple[list[list[int]], bool],
                tuple[list[list[int]], bool],
                tuple[list[list[int]], bool],
                tuple[list[list[int]], bool],
                tuple[list[list[int]], bool],
            ],
            tuple[
                list[int],
                list[tuple[tuple[str, str], list[int]]],
                list[tuple[str, list[int]]],
                list[tuple[str, list[int]]],
            ],
        ]
        | None
    ): ...

def build_native_scope_index(
    resources: list[tuple[str, str, str, str]],
    declarations: list[
        tuple[
            str,
            str,
            tuple[str, str] | None,
            str,
            int,
            str,
            str | None,
            str,
            str | None,
            list[tuple[str, str, tuple[str, str] | None]],
        ]
    ],
) -> NativeScopeIndex | None: ...

class NativeConfigError:
    class_name: str
    message: str
    code: str | None
    help: str | None
    key: str | None

def parse_model_header_metadata(
    header: tuple[object, object],
    source: tuple[dict[str, Any], str],
    classes: dict[str, object],
) -> tuple[tuple[Any, ...] | NativeConfigError, tuple[Any, ...] | NativeConfigError | None]: ...
def expand_config_templates(
    value: object,
    sources: tuple[dict[str, object], object, dict[str, str | None]],
    flags: tuple[bool, bool, bool, str],
) -> tuple[object, list[tuple[str, str]]]: ...
def expand_effective_vars(
    raw_values: dict[str, object], environment: object
) -> tuple[object, list[tuple[str, str]]]: ...

class NativeModelConfigBuilder:
    def __init__(
        self,
        layers: tuple[dict[str, object], dict[str, dict[str, object]], tuple[type, ...]],
        sources: tuple[dict[str, object], object],
        target: tuple[tuple[str | None, str], tuple[str | None, str | None] | None],
        python: tuple[tuple[int, int], str],
    ) -> None: ...
    def path_default(self, model_path: str) -> str | NativeConfigError | None: ...
    def build(
        self, header: dict[str, object], matched_path_default: str | None, model_name: str
    ) -> (
        tuple[
            dict[str, object],
            tuple[str, ...],
            tuple[str | None, bool, str | None],
            tuple[tuple[int | None, bool] | None, str | None],
            list[tuple[str, str]],
        ]
        | NativeConfigError
    ): ...

class NativeModelValidator:
    def __init__(
        self,
        names: tuple[set[str], set[str], set[str], set[str], set[str]],
        custom_materializations: set[str],
        microbatch_concurrency: bool,
        python: tuple[tuple[int, int], str],
    ) -> None: ...
    def validate(
        self,
        values: dict[str, object],
        model: tuple[str, str, str],
        facts: tuple[list[tuple[str, str, bool]], Sequence[str] | None, bool, bool],
    ) -> int | NativeConfigError | None: ...
    def references(
        self, model: tuple[str, str], references: list[tuple[str, str, bool]]
    ) -> int | NativeConfigError | None: ...

class SqlReferenceScanner:
    def __init__(self, syntax: dict[str, object]) -> None: ...
    def extract(
        self, sql: str
    ) -> (
        tuple[
            tuple[
                list[tuple[str, str, str | None, int | None]],
                list[tuple[str, str, int, str, str, str]],
            ],
            None,
        ]
        | tuple[None, tuple[str, int]]
    ): ...

def scope_expected_model_names(
    texts: list[tuple[str, str]], scenario: bool, syntax: dict[str, object]
) -> list[tuple[str | None, list[str]]]: ...
def scope_test_ctes(
    texts: list[tuple[str, str]], syntax: dict[str, object]
) -> list[tuple[str | None, list[tuple[str, str]]]]: ...
def extract_sql_scenario_json(sql: str, file_label: str, syntax: dict[str, object]) -> str: ...

class SqlTestTargetCatalog:
    def __init__(
        self,
        models: set[str],
        sources: set[str],
        seeds: set[str],
        resources: tuple[set[str], set[str]],
    ) -> None: ...
    def unknown_test_target(
        self,
        file_label: str,
        targets: tuple[list[str], list[str], list[str], list[str], list[str], list[str], list[str]],
    ) -> str | None: ...
    def scenario_source_error(
        self, file_label: str, ctes: list[tuple[str, bool, list[str]]]
    ) -> str | None: ...

def omitted_ceremonial_select(sql: str, syntax: dict[str, object]) -> int | None: ...
def scan_test_parameter_references(
    sql: str, declared: list[str], owner: str
) -> tuple[list[tuple[int, int, str]], str | None]: ...
def cursor_intrinsics_rejection(
    sql: str, reserved_markers: list[str], context: str, python: tuple[tuple[int, int], str]
) -> str | None: ...
def validated_model_cursor_intrinsics(
    sql: str,
    reserved_markers: list[str],
    model: tuple[str, object, object],
    python: tuple[tuple[int, int], str],
) -> tuple[str | None, str | None]: ...
def replace_cursor_intrinsics(
    sql: str, context: str, replacements: tuple[str, str], python: tuple[tuple[int, int], str]
) -> tuple[str, bool, str | None]: ...
def parse_function_header_values(
    header_values: dict[str, object], python: bool, relative_path: str
) -> tuple[
    list[tuple[str, str, str]],
    str | None,
    list[tuple[str, str, str]] | None,
    list[str],
    str | None,
    str | None,
    str | None,
    list[str],
    tuple[str, str] | None,
]: ...
def resolve_function_namespace_values(inputs: dict[str, object]) -> list[str | None]: ...
def pair_seed_files(
    declarations: list[str], stems: list[str]
) -> tuple[list[int], None] | tuple[None, int]: ...
def render_attached_generic_audit(
    labels: tuple[str, str],
    sql: tuple[str, str | None],
    arguments: tuple[list[tuple[str, str]], dict[str, object]],
    policies: dict[str, object],
) -> tuple[str | None, str, str | None, str, str, str | None]: ...
def parse_macro_arguments(text: str, nested: list[tuple[int, int]]) -> tuple[object, ...]: ...
def scan_sql_declaration_references(
    sqls: list[str], python_version: tuple[int, int], unicode_version: str
) -> list[tuple[list[tuple[int, str, str | None, int, int]], int | None]]: ...
def interpolate_sql_batch(
    sqls: list[tuple[str, str]],
    sources: tuple[
        Mapping[str, object],
        Mapping[str, str],
        Mapping[str, str | None] | None,
        Callable[..., str],
    ],
    python_version: tuple[int, int],
    unicode_version: str,
) -> list[
    tuple[str | None, list[tuple[int, int, int, int]], list[tuple[str, str]], str | None]
]: ...
def scan_macro_call_sites(
    sql: str, python_version: tuple[int, int], unicode_version: str
) -> list[tuple[int, int, str, list[str], bool]] | None: ...
def splice_macro_calls(
    sql: str, sites: list[tuple[int, int]], outputs: list[str]
) -> tuple[str, list[tuple[int, int, int, int]]]: ...

class MacroCallMemo:
    def __init__(self) -> None: ...
    def lookup(
        self, class_id: int, call_text: str
    ) -> tuple[str, list[tuple[str, str]], list[tuple[int, str, str]]] | None: ...
    def record(
        self,
        class_id: int,
        call_text: str,
        entry: tuple[str, list[tuple[str, str]], list[tuple[int, str, str]]],
    ) -> None: ...
    def stats(self) -> tuple[int, int, int]: ...
    def attach_store(self, path: str, environment: str) -> tuple[bytes, int]: ...
    def discard_store(self) -> None: ...
    def set_persistent_class(self, class_id: int, class_text: str) -> None: ...
    def store_stats(self) -> tuple[int, int]: ...
    def save_store(self, path: str, metadata: bytes) -> int | None: ...

class SqlTestScanStore:
    def __init__(self, path: str, environment: str) -> None: ...
    def get(self, key_parts: list[str]) -> bytes | None: ...
    def put(self, key_parts: list[str], value: bytes) -> None: ...
    def save(self, path: str) -> int | None: ...

def content_digest(parts: list[str]) -> str: ...
def fingerprint_project_files(root: str, excluded_files: list[str]) -> str: ...
def digest_files(paths: list[str]) -> list[str | None]: ...

# Native analysis: type system.
def normalize_type(
    type_sql: str, dialect: str
) -> tuple[tuple[str, str, str | None, str | None, str | None], str | None]: ...

# Native analysis: model analysis session.
type _AnalysisDiagnosticRow = tuple[str, str, int | None, int | None, int | None, int | None, str]

type _PivotContractRow = tuple[
    str,
    tuple[
        bool,
        list[tuple[str, str | None, str]],
        list[tuple[str, str | None]],
        list[str],
        str | None,
        bool,
    ]
    | None,
]

class NativeModelAnalysisSession:
    @property
    def fact_models(self) -> list[str]: ...
    def run(
        self,
    ) -> (
        tuple[
            list[tuple[str, list[tuple[str, str]]]],
            list[
                tuple[
                    str,
                    int,
                    str | None,
                    list[tuple[str, list[tuple[str, str]]]],
                    list[_AnalysisDiagnosticRow],
                    list[tuple[str, int, int, list[tuple[str, str, str]]]] | None,
                ]
            ],
            list[str],
        ]
        | None
    ): ...
    def provide(
        self,
        results: list[
            tuple[
                int,
                bool,
                list[tuple[str, str | None, str]] | None,
                bool,
                bool,
                list[_AnalysisDiagnosticRow],
                bool,
            ]
        ],
        /,
    ) -> bool: ...
    def finish(
        self,
    ) -> (
        tuple[
            list[
                tuple[
                    bool,
                    list[tuple[str, str | None, str]] | None,
                    str,
                    list[tuple[str, int, int, list[tuple[str, str, str]]]],
                    bool,
                    bool,
                    list[_AnalysisDiagnosticRow],
                    bool,
                    str,
                ]
            ],
            list[tuple[str, list[tuple[str, str]]]],
            list[str],
            list[
                tuple[
                    str,
                    tuple[
                        bool,
                        list[tuple[str, str | None, str]],
                        list[tuple[str, str | None]],
                        list[str],
                        str | None,
                        bool,
                    ]
                    | None,
                ]
            ],
        ]
        | None
    ): ...
    def prove_dynamic_contracts(
        self, models: list[tuple[str, list[tuple[str, str, str, str, str, str | None]]]], /
    ) -> list[_PivotContractRow] | None: ...
    @property
    def failure(self) -> str | None: ...
    @property
    def sharing(self) -> tuple[int, int]: ...
    @property
    def cache_stats(self) -> tuple[int, int, int, str | None] | None: ...

def start_model_analysis_session(
    catalog: object,
    request: tuple[object, ...],
    cache: tuple[str, str] | None = None,
    adapter_rules: tuple[dict[str, Callable[..., object]], type] | None = None,
) -> NativeModelAnalysisSession | None: ...
def prove_dynamic_column_contracts(
    request: tuple[
        str,
        list[tuple[str, list[tuple[str, str]]]],
        list[tuple[str, list[tuple[str, str]]]],
        list[tuple[str, list[tuple[str, str]]]],
        list[tuple[str, list[tuple[str, str, str, str, str, str | None]]]],
        list[tuple[str, list[tuple[str, str, str, str, str, str | None]]]],
    ],
    /,
) -> list[_PivotContractRow] | None: ...
def infer_expression_source_shapes(
    catalog: object, request: tuple[str, bool, list[tuple[str, str]], list[str]], /
) -> tuple[list[tuple[bool, list[tuple[str, str]] | None]], str | None]: ...
def _oracle_cte_fact_recovery(
    request: tuple[
        str,
        str,
        list[tuple[str, list[tuple[str, str]]]],
        list[tuple[str, str]],
        list[tuple[str, str]] | None,
        bool,
        bool,
    ],
    /,
) -> tuple[str | None, list[tuple[str, str]], list[tuple[str, str]], list[str], list[str]]: ...

# Native analysis: semantic completion.
class SemanticTypeRecovery:
    @property
    def status(self) -> str: ...
    @property
    def deferral(self) -> str | None: ...
    @property
    def poisoned(self) -> list[tuple[str, str]]: ...
    @property
    def revalidated(self) -> list[int]: ...
    def finish(
        self, revised: list[list[tuple[str, int | None, int | None]]], /
    ) -> tuple[list[tuple[int, str | None]], list[list[int]]] | None: ...

def plan_semantic_type_recovery(
    catalog: object,
    request: tuple[
        str | None,
        list[
            tuple[
                str,
                str,
                list[str] | None,
                list[str],
                list[tuple[str, list[tuple[str, str]]]] | None,
                list[tuple[int, str, str, bool]],
                list[tuple[int, str, str, int | None, int | None]],
            ]
        ],
        list[tuple[int, str, bool, str | None]],
    ],
    session: NativeModelAnalysisSession | None = None,
    /,
) -> SemanticTypeRecovery: ...
def check_semantic_metadata_rows(
    catalog: object,
    request: tuple[
        str | None,
        list[tuple[str, str]],
        list[tuple[str, list[tuple[str, str]]]],
        list[tuple[str, list[tuple[str, str]]]],
        list[
            tuple[
                str,
                str,
                str,
                bool,
                bool,
                list[tuple[str, list[str]]],
                list[tuple[str, list[str]]],
                str | None,
                str | None,
            ]
        ],
        list[str],
        list[tuple[str, str | None, int]],
        list[tuple[int, list[tuple[str, list[str]]]]],
    ],
    /,
) -> tuple[
    str | None,
    list[tuple[list[tuple[str, str, int, int]], list[tuple[str, str, int, int]]]],
    list[tuple[int, tuple[str, str, int, int]]],
    list[tuple[int, tuple[str, str, int, int], int]],
    list[str],
]: ...
def complete_semantic_checks(
    catalog: object,
    request: tuple[
        str | None,
        list[
            tuple[
                int,
                str,
                str,
                str | None,
                str | None,
                int | None,
                int | None,
                tuple[int, int, int | None, int | None] | None,
                str | None,
                list[str],
            ]
        ],
        list[
            tuple[
                str,
                str,
                str,
                list[str] | None,
                list[tuple[str, list[tuple[str, str]]]] | None,
                list[str],
                str | None,
            ]
        ],
        list[tuple[str, list[tuple[str, str]]]],
    ],
    session: NativeModelAnalysisSession | None = None,
    /,
) -> tuple[
    str | None,
    list[
        tuple[
            int,
            str,
            str | None,
            list[str],
            tuple[int, int, int | None, int | None] | None,
            int | None,
            int | None,
            bool,
        ]
    ],
    list[list[int]] | None,
    list[tuple[int | None, tuple[int, str, str, str] | None]],
]: ...

# Native analysis: contracts.
def evaluate_native_model_contracts(
    request: tuple[
        str,
        bool,
        list[
            tuple[
                str,
                str | None,
                tuple[list[tuple[str, str | None, bool, bool]], list[tuple[str, str]], bool, bool]
                | None,
                list[tuple[str, str | None, bool]] | None,
                bool,
                tuple[bool, str | None, list[tuple[str, str | None]]] | None,
                list[str],
            ]
        ],
    ],
    /,
) -> list[
    list[
        tuple[
            str,
            bool,
            str,
            str | None,
            int | None,
            str | None,
            tuple[str, str] | None,
            str,
        ]
    ]
]: ...
def native_promotion_conflicts(
    request: tuple[str | None, str, str, list[tuple[str, str | None, str | None, str | None]]],
    /,
) -> list[tuple[int, str, str, str]]: ...

# Native analysis: column lineage facts.
def build_fast_column_lineage(
    catalog: object,
    request: tuple[str | None, list[tuple[str, str, list[str]]], list[tuple[bool, str, list[str]]]],
    /,
) -> list[tuple[str, list[tuple[str, str, str, list[tuple[str, str, str]]]], bool, str | None]]: ...

# Native analysis: SQL test planning glue.
def plan_compiled_sql_tests(
    request: NativeSqlTestPlanningRequest, /
) -> tuple[list[NativeSqlTestPlanRow], int, int]: ...
def resolve_compiled_sql_test_chains(request: NativeSqlTestChainRequest, /) -> list[list[str]]: ...
def assemble_compiled_sql_tests(
    request: NativeSqlTestAssemblyRequest, /
) -> list[NativeSqlTestAssemblyRow]: ...

# Native analysis: compiled project assembly.
def check_native_sql_syntax(
    request: tuple[str, list[tuple[str, list[tuple[str, str]]]]], /
) -> tuple[bool | None, str | None]: ...
def assemble_project_resource_facts(
    request: tuple[
        str,
        tuple[str | None, str | None, str | None] | None,
        tuple[str | None, str | None, str | None, str | None],
        list[tuple[str, str, str]],
        list[tuple[str, str | None]],
        list[tuple[list[tuple[str, str, str | None]], list[tuple[str, list[tuple[str, str]]]]]],
        list[tuple[str, bool, str | None, str | None]],
        list[tuple[str, str | None, str | None]],
        list[list[tuple[str, str, str | None]]],
        list[tuple[list[tuple[str, str, str | None]], tuple[str, str] | None]],
    ],
    /,
) -> tuple[
    tuple[
        list[list[tuple[str, str]]],
        list[tuple[str | None, str | None] | None],
        list[tuple[str | None, str | None, str | None, str | None]],
        list[list[tuple[str, str]]],
        list[list[tuple[str, str]]],
        list[tuple[str, str]],
    ]
    | None,
    str | None,
]: ...

# Internal oracle hooks for tests that compare native foundations with Python; not an API.
def _oracle_json_dumps(dialect_json: str, value_json: str) -> str: ...
def _oracle_text_positions(
    data: bytes, byte_offsets: list[int]
) -> tuple[str, list[tuple[int, int, int] | None]]: ...
def _oracle_yaml_load(text: str) -> str: ...
def _oracle_toml_load(text: str) -> str: ...
def _oracle_project_config(project_dir: str) -> str: ...
def _oracle_python_alnum(
    python_version: tuple[int, int], unicode_version: str, code_points: list[int]
) -> list[bool] | None: ...
def _oracle_cleandoc(
    python_version: tuple[int, int], unicode_version: str, texts: list[str]
) -> list[str] | None: ...
def _oracle_close_matches(
    word: str, possibilities: list[str], count: int, cutoff: float
) -> list[str]: ...
def function_type_error(type_sql: str, adapter_name: str, context: str) -> str | None: ...
