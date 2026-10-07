"""Private SQLBuild native engine bindings."""

from typing import TypedDict

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
) -> list[tuple[str, tuple[object, ...]]] | None: ...
def discover_sql_test_files(
    request: dict[str, object], tree: NativeProjectTree
) -> list[tuple[str, tuple[object, ...]]] | None: ...
def discover_scenario_files(
    request: dict[str, object], tree: NativeProjectTree
) -> list[tuple[str, tuple[object, ...]]] | None: ...
def load_yaml_files(relative_paths: list[str], tree: NativeProjectTree) -> list[object] | None: ...
def discover_declaration_layout(
    tree: NativeProjectTree,
) -> (
    tuple[
        list[tuple[str, str, str, str, str | None, str]] | None,
        list[tuple[str, str]] | None,
    ]
    | None
): ...

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
def substitute_static_project_vars(
    sqls: list[str], variables: list[tuple[str, str]]
) -> list[tuple[int, str | None]]: ...
def extract_static_sql_references(
    sql: str,
) -> list[tuple[str, str, str | None, int | None]] | None: ...

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
