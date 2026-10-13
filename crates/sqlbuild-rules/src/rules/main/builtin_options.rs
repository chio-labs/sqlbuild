//! `builtin_options`: the options each built-in rule declares.

use crate::rules::models::{BuiltinOption, BuiltinOptionKind};

const fn boolean(name: &'static str, description: &'static str) -> BuiltinOption {
    BuiltinOption {
        kind: BuiltinOptionKind::Boolean,
        name,
        description,
    }
}

/// The declared options of the built-in rule `code`, in declaration order.
#[must_use]
pub fn builtin_options(code: &str) -> Vec<BuiltinOption> {
    match code {
        "SQBRCONTRACT102" => vec![boolean(
            "allow_numeric_indicators",
            "Accept numeric is_/has_/can_ indicator columns.",
        )],
        "SQBRCONTRACT103" => vec![
            boolean(
                "allow_date_for_at",
                "Accept DATE for columns ending in _at.",
            ),
            boolean(
                "allow_numeric_epoch",
                "Accept numeric epoch values for timestamp-named columns.",
            ),
            boolean(
                "allow_encoded_values",
                "Accept string or variant encoded timestamp values.",
            ),
        ],
        "SQBRCONTRACT104" => vec![
            boolean(
                "allow_timestamps",
                "Accept timestamp types for columns ending in _date.",
            ),
            boolean(
                "allow_encoded_values",
                "Accept string or variant encoded date values.",
            ),
        ],
        "SQBRTEST203" => vec![BuiltinOption {
            kind: BuiltinOptionKind::StringList,
            name: "allowed_tests",
            description: "Reviewed SQL test names that may assert only that empty inputs produce \
                          no rows; listed tests count toward min_tests_per_model.",
        }],
        _ => Vec::new(),
    }
}
