//! The JSON payload of a `sqb dbt` plan.

use crate::cli_text::models::DbtInteropPlanText;
use crate::json::models::JsonValue;

fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

fn texts(values: &[String]) -> JsonValue {
    JsonValue::Array(values.iter().map(|value| text(value)).collect())
}

fn argvs(values: &[Vec<String>]) -> JsonValue {
    JsonValue::Array(values.iter().map(|argv| texts(argv)).collect())
}

fn object(fields: Vec<(&str, JsonValue)>) -> JsonValue {
    JsonValue::Object(
        fields
            .into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect(),
    )
}

fn skip_reason(reason: Option<&String>) -> JsonValue {
    reason.map_or(JsonValue::Null, |reason| text(reason))
}

/// The plan's dbt and SQLBuild work as the JSON payload Python built.
pub(crate) fn dbt_plan_payload(plan: &DbtInteropPlanText) -> JsonValue {
    object(vec![
        ("command", text(&plan.command)),
        (
            "dbt",
            object(vec![
                ("argv", texts(&plan.dbt_argv)),
                ("supplemental_argvs", argvs(&plan.supplemental_dbt_argvs)),
                ("selected_unique_ids", texts(&plan.dbt_selected_unique_ids)),
                ("required_unique_ids", texts(&plan.dbt_required_unique_ids)),
                (
                    "required_selector_terms",
                    texts(&plan.dbt_required_selector_terms),
                ),
                ("skipped", JsonValue::Bool(plan.dbt_skip_reason.is_some())),
                ("skip_reason", skip_reason(plan.dbt_skip_reason.as_ref())),
            ]),
        ),
        (
            "sqlbuild",
            object(vec![
                ("argvs", argvs(&plan.sqlbuild_argvs)),
                ("selected_models", texts(&plan.sqlbuild_models)),
                (
                    "skipped",
                    JsonValue::Bool(plan.sqlbuild_skip_reason.is_some()),
                ),
                (
                    "skip_reason",
                    skip_reason(plan.sqlbuild_skip_reason.as_ref()),
                ),
            ]),
        ),
        (
            "anchors",
            JsonValue::Array(
                plan.anchors
                    .iter()
                    .map(|(term, unique_ids)| {
                        object(vec![
                            ("term", text(term)),
                            ("unique_ids", texts(unique_ids)),
                        ])
                    })
                    .collect(),
            ),
        ),
        (
            "path_translations",
            JsonValue::Array(
                plan.path_translations
                    .iter()
                    .map(|(original, translated)| {
                        object(vec![("from", text(original)), ("to", text(translated))])
                    })
                    .collect(),
            ),
        ),
        ("warnings", texts(&plan.warnings)),
    ])
}
