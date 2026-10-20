//! The fields discovery reports for SQL hook entries.

/// The fields a SQL hook entry reports, in output order.
pub(crate) const SQL_HOOK_OUTPUT_FIELDS: [&str; 6] = [
    "statement",
    "name",
    "relative_path",
    "definition_sql",
    "kwargs",
    "description",
];
