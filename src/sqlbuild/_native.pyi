"""Private SQLBuild native engine bindings."""

from collections.abc import Sequence
from typing import Any, TypedDict

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
def parse_model_header_metadata(
    requests: list[tuple[object, object, dict[str, Any]]], classes: dict[str, object]
) -> list[tuple[tuple[Any, ...], tuple[Any, ...]] | str]: ...
def config_contains_template(value: object) -> bool | None: ...
def config_contains_macro_call(value: object) -> bool | None: ...
def expand_config_templates(
    value: object,
    sources: tuple[dict[str, object], object, dict[str, str | None]],
    flags: tuple[bool, bool, bool],
) -> tuple[object, list[tuple[str, str]]] | str: ...

class NativeModelConfigBuilder:
    def __init__(
        self,
        layers: tuple[dict[str, object], dict[str, dict[str, object]], tuple[type, ...]],
        sources: tuple[dict[str, object], object],
        run: tuple[str | None, str],
        target_namespace: tuple[str | None, str | None] | None,
    ) -> None: ...
    def path_default(self, model_path: str) -> tuple[bool, str | None]: ...
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
        | None
    ): ...

class NativeModelValidator:
    def __init__(
        self,
        names: tuple[set[str], set[str], set[str], set[str], set[str]],
        custom_materializations: set[str],
        microbatch_concurrency: bool,
    ) -> None: ...
    def accepts(
        self,
        values: dict[str, object],
        model: tuple[str, str],
        facts: tuple[tuple[object, ...], list[str] | None, bool, bool],
    ) -> bool: ...

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
        | None
    ): ...

def scope_expected_model_names(
    sqls: list[str], syntax: dict[str, object]
) -> list[list[str] | None]: ...
def extract_sql_scenario_json(sql: str, file_label: str) -> str | None: ...

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

def omitted_ceremonial_select(sql: str, syntax: dict[str, object]) -> tuple[bool, int | None]: ...
def scan_test_parameter_references(
    sql: str, declared: list[str]
) -> list[tuple[int, int, str]] | None: ...
def sql_free_of_cursor_intrinsics(sql: str, reserved_markers: list[str]) -> bool: ...
def parse_function_header_values(
    header_values: dict[str, object], python: bool
) -> (
    tuple[
        list[tuple[str, str, str]],
        str | None,
        list[tuple[str, str, str]] | None,
        list[str],
        str | None,
        str | None,
        str | None,
        list[str],
    ]
    | None
): ...
def resolve_function_namespace_values(inputs: dict[str, object]) -> list[str | None]: ...
def pair_seed_files(
    declarations: list[str], stems: list[str]
) -> tuple[list[int], None] | tuple[None, int]: ...
def render_attached_generic_audit(
    sql: tuple[str, str | None],
    arguments: tuple[dict[str, object], dict[str, object]],
    policies: dict[str, object],
) -> tuple[str, str | None, str, str] | None: ...
def scan_sql_declaration_references(
    sqls: list[str],
) -> list[tuple[list[tuple[int, str, str | None, int, int]], int | None] | None]: ...
def substitute_static_project_vars(
    sqls: list[str], variables: list[tuple[str, str]]
) -> list[tuple[int, str | None]]: ...
def extract_static_sql_references(
    sql: str,
) -> list[tuple[str, str, str | None, int | None]] | None: ...
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
) -> tuple[tuple[str, str, int | None, int | None, int | None], str | None] | None: ...

# Native analysis: model analysis session.

# Native analysis: semantic completion.

# Native analysis: contracts.

# Native analysis: column lineage facts.
def build_fast_column_lineage(
    catalog: object,
    request: tuple[str | None, list[tuple[str, str, list[str]]], list[tuple[bool, str, list[str]]]],
    /,
) -> list[tuple[str, list[tuple[str, str, str, list[tuple[str, str, str]]]], bool, str | None]]: ...

# Native analysis: SQL test planning glue.

# Native analysis: compiled project assembly.

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
