//! Planner enumerations declared natively.

/// Each planner `StrEnum`: its name and its members with their values, in declaration order.
pub(crate) const PLANNER_STR_ENUMS: &[(&str, &[(&str, &str)])] = &[
    (
        "GraphResourceKind",
        &[
            ("MODEL", "model"),
            ("SEED", "seed"),
            ("SOURCE", "source"),
            ("FUNCTION", "function"),
        ],
    ),
    (
        "ChangeKind",
        &[
            ("FIRST_RUN", "first_run"),
            ("RENAMED", "renamed"),
            ("QUERY_CHANGED", "query_changed"),
            ("FUNCTION_CHANGED", "function_changed"),
            ("CONFIG_CHANGED", "config_changed"),
            ("SCHEMA_CHANGED", "schema_changed"),
            ("NO_CHANGE", "no_change"),
        ],
    ),
    (
        "SchemaChangeKind",
        &[
            ("COLUMN_ADDED", "column_added"),
            ("COLUMN_REMOVED", "column_removed"),
            ("COLUMN_TYPE_CHANGED", "column_type_changed"),
        ],
    ),
    (
        "SchemaColumnSource",
        &[("YML", "yml"), ("SQL_ANALYSIS", "sql_analysis")],
    ),
    ("CursorWatermarkMode", &[("ALL", "all"), ("ANY", "any")]),
    (
        "SchemaActionKind",
        &[
            ("ADD_COLUMN", "add_column"),
            ("DROP_COLUMN", "drop_column"),
            ("ALTER_COLUMN_TYPE", "alter_column_type"),
        ],
    ),
    (
        "WarningSeverity",
        &[("ERROR", "error"), ("WARNING", "warning"), ("INFO", "info")],
    ),
];
