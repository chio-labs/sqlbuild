//! Type names and defaults that decide a normalized type's family and spelling.

pub(crate) const BOOLEAN_TYPE_NAMES: &[&str] = &["BOOL", "BOOLEAN"];
pub(crate) const DATE_TYPE_NAME: &str = "DATE";
pub(crate) const DATETIME_TYPE_NAME: &str = "DATETIME";
pub(crate) const DECIMAL_TYPE_NAMES: &[&str] =
    &["BIGDECIMAL", "BIGNUMERIC", "DECIMAL", "NUMBER", "NUMERIC"];
pub(crate) const FLOAT_TYPE_NAMES: &[&str] = &["DOUBLE", "FLOAT", "FLOAT64", "REAL"];
pub(crate) const INTEGER_TYPE_NAMES: &[&str] = &[
    "BIGINT", "INT", "INT64", "INTEGER", "LONG", "SMALLINT", "TINYINT",
];
pub(crate) const POLYGLOT_CUSTOM_TYPE_NAME: &str = "CUSTOM";
pub(crate) const STRING_TYPE_NAMES: &[&str] = &["CHAR", "CHARACTER", "STRING", "TEXT", "VARCHAR"];
pub(crate) const TIMESTAMP_TYPE_NAMES: &[&str] =
    &["TIMESTAMP", "TIMESTAMPLTZ", "TIMESTAMPNTZ", "TIMESTAMPTZ"];
pub(crate) const TIMESTAMP_TYPE_TOKEN: &str = "TIMESTAMP";
pub(crate) const BIGNUMERIC_TYPE_NAME: &str = "BIGNUMERIC";
pub(crate) const CUSTOM_NORMALIZATION_TYPE_NAMES: &[&str] = &["BIGNUMERIC", "FLOAT64", "INT64"];
pub(crate) const FLOAT_WIRE_TYPE_NAME: &str = "FLOAT64";
pub(crate) const INTEGER_PARSE_TYPE_NAMES: &[&str] = &["BIGINT", "INT"];
pub(crate) const DEFAULT_TEXT_LENGTH: i64 = 16_777_216;
pub(crate) const INTEGER_PRECISION: i64 = 38;
pub(crate) const INTEGER_SCALE: i64 = 0;
pub(crate) const NORMALIZED_LTZ_INPUT_TYPE_NAME: &str = "TIMESTAMPLTZ";
pub(crate) const NORMALIZED_NTZ_INPUT_TYPE_NAMES: &[&str] = &["TIMESTAMP", "TIMESTAMPNTZ"];
pub(crate) const NORMALIZED_TZ_INPUT_TYPE_NAME: &str = "TIMESTAMPTZ";
pub(crate) const TEXT_TYPE_NAME: &str = "TEXT";
pub(crate) const UNBOUNDED_TEXT_TYPE_NAMES: &[&str] = &["STRING", "TEXT", "VARCHAR"];
/// Polyglot `data_type` tags whose Python spelling drops the word separator.
pub(crate) const POLYGLOT_TYPE_NAME_ALIASES: &[(&str, &str)] = &[
    ("BIG_INT", "BIGINT"),
    ("SMALL_INT", "SMALLINT"),
    ("TINY_INT", "TINYINT"),
    ("VAR_CHAR", "VARCHAR"),
];
/// The function call depth limit SQLBuild passes to every Polyglot parse.
pub(crate) const MAX_FUNCTION_CALL_DEPTH: usize = 512;
/// Characters Python's `str.strip()` and the `\s` regex class treat as ASCII whitespace.
pub(crate) const PYTHON_ASCII_WHITESPACE: &[u8] = b" \t\n\r\x0b\x0c\x1c\x1d\x1e\x1f";
