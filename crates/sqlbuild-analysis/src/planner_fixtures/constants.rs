//! Empty fixture marker pattern.

pub(crate) const MARKER_PATTERNS: [&str; 4] = [
    r#"__ref\("([^"]+)"\)"#,
    r#"__seed\("([^"]+)"\)"#,
    r#"__source\("([^"]+)"\)"#,
    r#"__dbt_ref\("[^"]+"[\s\x1c-\x1f]*,[\s\x1c-\x1f]*"([^"]+)"\)"#,
];

pub(crate) const EMPTY_PATTERN: &str = r"(?i)^[\s\x1c-\x1f]*SELECT[\s\x1c-\x1f]+\*[\s\x1c-\x1f]+FROM[\s\x1c-\x1f]+__empty_fixture[\s\x1c-\x1f]*\([\s\x1c-\x1f]*\)[\s\x1c-\x1f]*$";
pub(crate) const READ_CACHE_CAPACITY: usize = 4096;
pub(crate) const FIXTURE_WHITESPACE: &str = r"[\s\x1c-\x1f]";
pub(crate) const COLLECTION_TYPES: [&str; 6] =
    ["ARRAY", "LIST", "MAP", "OBJECT", "STRUCT", "VARIANT"];
