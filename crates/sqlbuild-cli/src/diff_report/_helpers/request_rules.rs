//! The individual `sqb diff` flag rules.

use crate::diff_report::errors::DiffUserError;
use crate::diff_report::models::DiffRequestFacts;

pub(crate) fn user_error(message: &str, code: &str) -> DiffUserError {
    DiffUserError {
        message: message.to_owned(),
        code: code.to_owned(),
        help: None,
    }
}

fn not_positive(value: Option<i64>) -> bool {
    value.is_some_and(|value| value <= 0)
}

fn blank(value: Option<&String>) -> bool {
    value.is_some_and(|value| value.trim().is_empty())
}

/// The first violated rule that applies to model and raw-query diffs alike.
pub(crate) fn common_violation(request: &DiffRequestFacts) -> Option<(&'static str, &'static str)> {
    let modes: usize = usize::from(request.full)
        + usize::from(request.schema_only)
        + usize::from(request.bounded.is_some());
    let mut lowered: Vec<String> = request
        .unique_key_override
        .iter()
        .map(|key| key.to_lowercase())
        .collect();
    lowered.sort();
    let total: usize = lowered.len();
    lowered.dedup();
    let rules: [(bool, &str, &str); 15] = [
        (
            modes > 1,
            "diff accepts at most one of --full, --schema-only, or --bounded",
            "C201",
        ),
        (
            not_positive(request.max_column_examples),
            "diff --max-column-examples must be positive",
            "C202",
        ),
        (
            not_positive(request.max_row_only_examples),
            "diff --max-row-only-examples must be positive",
            "C203",
        ),
        (
            not_positive(request.sample_rows),
            "diff --sample-rows must be positive",
            "C208",
        ),
        (
            request.exhaustive && request.sample_rows.is_some(),
            "diff --exhaustive cannot be combined with --sample-rows",
            "C209",
        ),
        (
            not_positive(request.max_models),
            "diff --max-models must be positive",
            "C210",
        ),
        (
            not_positive(request.max_columns),
            "diff --max-columns must be positive",
            "C211",
        ),
        (
            not_positive(request.max_value_length),
            "diff --max-value-length must be positive",
            "C246",
        ),
        (
            request.full_example_values && request.max_value_length.is_some(),
            "diff --full-example-values cannot be combined with --max-value-length",
            "C247",
        ),
        (
            request.full_example_values && request.suppress_example_values,
            "diff --full-example-values cannot be combined with --no-example-values",
            "C248",
        ),
        (
            request.unkeyed && !request.unique_key_override.is_empty(),
            "diff --unkeyed cannot be combined with --key",
            "C226",
        ),
        (
            request.unkeyed && (request.sample_rows.is_some() || request.sample_seed.is_some()),
            "unkeyed diff does not support sampling",
            "C222",
        ),
        (
            request.unkeyed && !request.tolerance_overrides.is_empty(),
            "unkeyed diff does not support tolerances",
            "C223",
        ),
        (
            request
                .unique_key_override
                .iter()
                .any(|key| key.trim().is_empty()),
            "diff --key values must not be empty",
            "C241",
        ),
        (
            lowered.len() != total,
            "diff --key values must be unique",
            "C242",
        ),
    ];
    rules
        .into_iter()
        .find(|(violated, _, _)| *violated)
        .map(|(_, message, code)| (message, code))
}

/// The first violated rule specific to raw-query diffs.
pub(crate) fn query_violation(request: &DiffRequestFacts) -> Option<(&'static str, &'static str)> {
    let left: bool = request.left_query || request.left_query_file;
    let right: bool = request.right_query || request.right_query_file;
    let keyed: bool = !request.unique_key_override.is_empty();
    let rules: [(bool, &str, &str); 12] = [
        (
            request.from_name.is_some() || request.to_name.is_some(),
            "raw-query diff does not accept FROM:TO",
            "C212",
        ),
        (
            !request.select.is_empty() || !request.exclude.is_empty(),
            "raw-query diff does not accept model selectors",
            "C213",
        ),
        (
            request.bounded.is_some(),
            "raw-query diff does not support --bounded; filter both raw queries explicitly",
            "C214",
        ),
        (
            request.max_models.is_some(),
            "raw-query diff does not accept --max-models",
            "C243",
        ),
        (
            blank(request.left_label.as_ref()),
            "raw-query diff --left-label must not be empty",
            "C249",
        ),
        (
            blank(request.right_label.as_ref()),
            "raw-query diff --right-label must not be empty",
            "C250",
        ),
        (!left, "raw-query diff requires a left query", "C216"),
        (
            request.left_query && request.left_query_file,
            "raw-query diff accepts either --left-query or --left-query-file, not both",
            "C217",
        ),
        (!right, "raw-query diff requires a right query", "C218"),
        (
            request.right_query && request.right_query_file,
            "raw-query diff accepts either --right-query or --right-query-file, not both",
            "C219",
        ),
        (
            request.schema_only && (request.unkeyed || keyed),
            "schema-only raw-query diff does not accept --key or --unkeyed",
            "C220",
        ),
        (
            !request.schema_only && keyed == request.unkeyed,
            "raw-query diff requires one or more --key values or explicit --unkeyed",
            "C221",
        ),
    ];
    rules
        .into_iter()
        .find(|(violated, _, _)| *violated)
        .map(|(_, message, code)| (message, code))
}

/// The first violated rule specific to model diffs.
pub(crate) fn model_violation(request: &DiffRequestFacts) -> Option<(&'static str, &'static str)> {
    let rules: [(bool, &str, &str); 3] = [
        (
            request.from_name.is_none(),
            "model diff requires FROM or FROM:TO",
            "C224",
        ),
        (
            request.selected_target.is_some(),
            "model diff does not accept --target",
            "C225",
        ),
        (
            request.left_label.is_some() || request.right_label.is_some(),
            "model diff does not accept query labels",
            "C251",
        ),
    ];
    rules
        .into_iter()
        .find(|(violated, _, _)| *violated)
        .map(|(_, message, code)| (message, code))
}
