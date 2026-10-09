//! Codes, help texts and patterns Python's semantic completion uses.

pub(crate) const UNKNOWN_COLUMN_CODE: &str = "B002";
pub(crate) const COMPARISON_CODE: &str = "B217";
pub(crate) const SQL_TEST_COLUMN_CODE: &str = "B302";
pub(crate) const SEMANTIC_CODE_PREFIX: &str = "B";
pub(crate) const MODEL_RESOURCE_TYPE: &str = "model";
pub(crate) const MAX_FUNCTION_CALL_DEPTH: u64 = 512;
pub(crate) const GENERIC_DIALECT: &str = "generic";
pub(crate) const OPEN_PARENTHESIS: &str = "(";
pub(crate) const CLOSE_PARENTHESIS: &str = ")";
pub(crate) const PROJECTION_SEPARATOR: &str = ",";
pub(crate) const TYPE_CODES: [&str; 10] = [
    "B210", "B211", "B212", "B213", "B214", "B215", "B216", "B217", "B218", "B219",
];
pub(crate) const MIN_ABBREVIATION_LENGTH: usize = 3;
pub(crate) const MAX_EDIT_DISTANCE: usize = 2;
pub(crate) const DISPLAY_LIMIT: usize = 10;
pub(crate) const PROJECT_CONFIG_FILENAME: &str = "sqlbuild_project.toml";
pub(crate) const SETTINGS_SECTION: &str = "settings";
pub(crate) const REQUIRE_SQL_ANALYSIS_KEY: &str = "require_sql_analysis";
pub(crate) const SETTING_SNIPPET_INDENT: &str = "            ";
pub(crate) const ADDITIONAL_HELP_SEPARATOR: &str = "\n  = help: ";
pub(crate) const TIMESTAMP_TYPE: &str = "TIMESTAMP";
pub(crate) const DATE_TYPE: &str = "DATE";
pub(crate) const BIGQUERY_DIALECT: &str = "bigquery";

pub(crate) const TYPE_WORDS_PATTERN: &str = r"(?i)\b(timestamp|integer|varchar|boolean|date|interval|double|float|decimal|numeric|bigint|smallint|text|time|string|binary|array|struct)\b";
pub(crate) const MISSING_PATTERN: &str = r"Unknown column '([^']+)'(?: in table '([^']+)')?";
pub(crate) const CONTEXT_SUFFIX_PATTERN: &str = r" \(context: [^)]*\)$";
pub(crate) const QUOTED_PIECE_PATTERN: &str = r"'[^']*'";
pub(crate) const OPERAND_PATTERN: &str = r"(?:TIMESTAMP\s+'[^']*'|DATE\s+'[^']*'|'(?:[^']|'')*'|-?\d+(?:\.\d+)?|[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)";
pub(crate) const QUALIFIER_PATTERN: &str = r#"(?:"((?:[^"]|"")+)"|([A-Za-z_]\w*))\.$"#;
pub(crate) const TEMPORAL_OPERAND_PATTERN: &str = r"(?i)\A(TIMESTAMP|DATE)\s*'";
pub(crate) const INTEGER_OPERAND_PATTERN: &str = r"\A-?\d+\z";
pub(crate) const DECIMAL_OPERAND_PATTERN: &str = r"\A-?\d+\.\d+\z";
pub(crate) const SQL_TEST_COLUMN_PATTERN: &str =
    r"'__(?:expected|ref)__(.+)' names unknown column '([^']+)'";

/// Python's `_SEMANTIC_HELP` catalogue.
pub(crate) const SEMANTIC_HELP: &[(&str, &str)] = &[
    ("B003", "qualify this column with the intended input alias"),
    (
        "B004",
        "give each referenced relation a visible alias in this scope",
    ),
    (
        "B005",
        "match the relation alias list to its available output columns",
    ),
    (
        "B101",
        "check the function spelling or declare the project function before using it",
    ),
    (
        "B102",
        "pass the number of arguments required by this function's signature",
    ),
    (
        "B210",
        "use an expression whose inferred type satisfies this SQL construct",
    ),
    ("B211", "use a Boolean predicate in this condition"),
    (
        "B212",
        "use operands supported by this arithmetic operator, or convert them explicitly",
    ),
    (
        "B213",
        "supply argument types supported by this function or conditional expression",
    ),
    (
        "B214",
        "make the assigned expression compatible with the destination type",
    ),
    (
        "B215",
        "align the corresponding types in each set-operation branch",
    ),
    (
        "B216",
        "return the same number of columns on both sides of this operation",
    ),
    (
        "B217",
        "compare compatible types using a correctly typed literal or explicit conversion",
    ),
    (
        "B218",
        "choose a supported source-to-target cast for this dialect",
    ),
    (
        "B219",
        "declare or cast this expression's unknown type so it can be checked",
    ),
    (
        "B230",
        "add this expression to GROUP BY or use it inside an aggregate",
    ),
    (
        "B231",
        "move this aggregate to SELECT or HAVING, or compute it in an input CTE",
    ),
    (
        "B232",
        "use this window function with a valid OVER clause and window context",
    ),
    (
        "B233",
        "use distinct names for relations or CTEs within this scope",
    ),
    ("B234", "use a valid constant bound for LIMIT or OFFSET"),
    (
        "B300",
        "change the metadata column name to an existing output column",
    ),
    (
        "B301",
        "align this declared metadata or audit value with the column or argument type",
    ),
    (
        "B302",
        "align the SQL-test fixture or expected columns with the tested resource's output",
    ),
];

/// Python's `_FINDING_KINDS`: a code test, then the singular and plural nouns.
pub(crate) const FINDING_KINDS: &[(&str, &str, &str)] = &[
    ("^B002$", "unknown column", "unknown columns"),
    ("^B003$", "ambiguous column", "ambiguous columns"),
    ("^B00[45]$", "reference error", "reference errors"),
    ("^B101$", "unknown function", "unknown functions"),
    ("^B102$", "function arity error", "function arity errors"),
    ("^B216$", "column count mismatch", "column count mismatches"),
    ("^B21\\d$", "type mismatch", "type mismatches"),
    (
        "^B23[0-2]$",
        "grouping or window error",
        "grouping or window errors",
    ),
    ("^B3\\d\\d$", "metadata mismatch", "metadata mismatches"),
];
