//! Wire values shared with Python's model analysis.

/// The native engine's request for Python's legacy type recovery.
pub(crate) const LEGACY_FALLBACK: &str = "native project type recovery requires legacy fallback";
/// Python logs this for a malformed per-model response.
pub(crate) const INVALID_NATIVE_RESPONSE: &str = "invalid native response";
/// Python's `UNKNOWN` column type.
pub(crate) const UNKNOWN_TYPE: &str = "UNKNOWN";
/// Python's `InferredNullability.UNKNOWN`.
pub(crate) const UNKNOWN_NULLABILITY: &str = "unknown";
/// Python's `InferredNullability` values by native code.
pub(crate) const NULLABILITY_BY_CODE: [&str; 3] = ["unknown", "non_null", "nullable"];
/// The transform and confidence code counts Python's enum tuples accept.
pub(crate) const TRANSFORM_CODES: u64 = 6;
pub(crate) const CONFIDENCE_CODES: u64 = 3;
/// Python's `COMPACT_ANALYSIS_RESPONSE_LENGTH`: a member's `[template, mappings]`.
pub(crate) const RESPONSE_LENGTH: usize = 2;
/// Python's `COMPACT_ANALYSIS_LEGACY_RESPONSE_LENGTH`: `[rows, has_star, flag]`.
pub(crate) const LEGACY_RESPONSE_LENGTH: usize = 3;
/// Python's `COMPACT_ANALYSIS_FACT_LENGTH`.
pub(crate) const FACT_LENGTH: usize = 6;
/// Python's `COMPACT_ANALYSIS_SOURCE_LENGTH`.
pub(crate) const SOURCE_LENGTH: usize = 3;
/// Python's `BINDING_SEVERITIES`.
pub(crate) const BINDING_SEVERITIES: [&str; 2] = ["error", "warning"];
/// Python's default binding message.
pub(crate) const DEFAULT_BINDING_MESSAGE: &str = "SQL binding failed";
/// Analysis workers per compact batch, as Python requests.
pub(crate) const COMPACT_WORKERS: usize = 4;
/// Python's `NATIVE_DIALECT_ALIASES`.
pub(crate) const DIALECT_ALIASES: [(&str, &str); 3] = [
    ("postgres", "postgresql"),
    ("motherduck", "duckdb"),
    ("sqlserver", "tsql"),
];
/// The quote that marks an exact identifier.
pub(crate) const QUOTED_IDENTIFIER_DELIMITER: char = '"';
/// Python's names for a legacy-analysis and an enrichment deferral.
pub(crate) const DEFERRAL_ANALYSIS: &str = "analysis";
pub(crate) const DEFERRAL_ENRICHMENT: &str = "enrichment";
/// Python's `ColumnTransformKind` compact codes.
pub(crate) const TRANSFORM_DIRECT: u8 = 0;
pub(crate) const TRANSFORM_CAST: u8 = 1;
pub(crate) const TRANSFORM_EXPRESSION: u8 = 2;
pub(crate) const TRANSFORM_AGGREGATION: u8 = 3;
pub(crate) const TRANSFORM_STAR: u8 = 4;
pub(crate) const TRANSFORM_CONSTANT: u8 = 5;
/// Python's `ColumnLineageConfidence` compact codes.
pub(crate) const CONFIDENCE_UNKNOWN: u8 = 0;
pub(crate) const CONFIDENCE_HIGH: u8 = 1;
pub(crate) const CONFIDENCE_MEDIUM: u8 = 2;
/// The `analyze_query` facts Python's re-analysis reads.
pub(crate) const SELECT_SHAPE: &str = "select";
pub(crate) const SET_OPERATION_SHAPE: &str = "set_operation";
pub(crate) const CAST_TRANSFORM: &str = "cast";
pub(crate) const FILTER_CONTEXT: &str = "filter";
pub(crate) const NULL_KEYWORD: &str = "NULL";
pub(crate) const RESOLVED_SOURCE_CONFIDENCE: &str = "resolved";
pub(crate) const WILDCARD: &str = "*";
/// SQLBuild's `analyze_query` complexity guard.
pub(crate) const MAX_FUNCTION_CALL_DEPTH: usize = 512;
/// The dialects whose dynamic pivots the compiler proves, and those with DuckDB's PIVOT form.
pub(crate) const SUPPORTED_PIVOT_DIALECTS: [&str; 3] = ["duckdb", "motherduck", "snowflake"];
pub(crate) const SIMPLIFIED_PIVOT_DIALECTS: [&str; 2] = ["duckdb", "motherduck"];
pub(crate) const DUCKDB_DIALECT: &str = "duckdb";
pub(crate) const MOTHERDUCK_DIALECT: &str = "motherduck";
/// The `to_dict()` node keys Python's dynamic pivot proof walks.
pub(crate) const PIVOT_AST_KIND: &str = "pivot";
pub(crate) const SELECT_AST_KIND: &str = "select";
pub(crate) const QUERY_AST_KINDS: [&str; 2] = ["query", "subquery"];
pub(crate) const CAST_AST_KIND: &str = "cast";
pub(crate) const COLUMN_AST_KIND: &str = "column";
pub(crate) const TABLE_AST_KIND: &str = "table";
pub(crate) const FUNCTION_AST_KIND: &str = "function";
pub(crate) const ALIAS_AST_KIND: &str = "alias";
pub(crate) const CTE_AST_KIND: &str = "cte";
pub(crate) const STAR_AST_KIND: &str = "star";
pub(crate) const DYNAMIC_VALUE_SOURCE_KINDS: [&str; 3] = ["pivot_any", "select", "query"];
pub(crate) const DEPENDENCY_FUNCTION_NAMES: [&str; 3] = ["__ref", "__source", "__seed"];
pub(crate) const TYPE_PRESERVING_AGGREGATES: [&str; 3] = ["ANY_VALUE", "MAX", "MIN"];
/// Python's `_render_type` names for cast targets.
pub(crate) const RENDERED_TYPE_NAMES: [(&str, &str); 12] = [
    ("big_int", "BIGINT"),
    ("bool", "BOOLEAN"),
    ("boolean", "BOOLEAN"),
    ("decimal", "DECIMAL"),
    ("double", "DOUBLE"),
    ("float", "FLOAT"),
    ("int", "INT"),
    ("integer", "INT"),
    ("text", "TEXT"),
    ("timestamp", "TIMESTAMP"),
    ("var_char", "VARCHAR"),
    ("varchar", "VARCHAR"),
];
/// The stack a standalone dynamic pivot proof parses on, as the analysis workers have.
pub(crate) const PIVOT_WORKER_STACK_BYTES: usize = 16 * 1024 * 1024;
/// Python's `COMPACT_RELATION_STUB_PREFIX`: the relation name a shared query binds instead.
pub(crate) const RELATION_STUB_PREFIX: &str = "__sqlbuild_project_input_";
/// Python's `COMPACT_REFERENCE_MARKER_PATTERN`: a reference call and the name it reads.
pub(crate) const REFERENCE_MARKER_PATTERN: &str =
    r#"__(ref|seed|source|dbt_ref)\((?:"[^"]+"\s*,\s*)?"([^"]+)"\)"#;
/// Python's `COMPACT_UNSTUBBED_REFERENCE_KIND`, a reference kind sharing never stubs.
pub(crate) const UNSTUBBED_REFERENCE_KIND: &str = "dbt_ref";
/// Python's `MIN_SHARED_BINDING_QUERY_MEMBERS`.
pub(crate) const MIN_SHARED_MEMBERS: usize = 2;
/// Text whose presence sends Python's qualifier search to its token scanner.
pub(crate) const QUALIFIED_SCAN_TOKENS: [&str; 5] = ["\"", "`", "[", "--", "/*"];
/// Python's `str.isspace` over ASCII.
pub(crate) const PYTHON_ASCII_SPACES: &str = " \t\n\r\x0b\x0c\x1c\x1d\x1e\x1f";
