//! JSON values of contract resources and findings.

use crate::contract_command::models::{ContractFindingText, ContractResourceText};
use crate::json::models::JsonValue;

pub(crate) fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

fn optional(value: Option<&String>) -> JsonValue {
    value.map_or(JsonValue::Null, |value| text(value))
}

fn finding(finding: &ContractFindingText) -> JsonValue {
    JsonValue::Object(vec![
        ("kind".to_owned(), text(&finding.kind)),
        ("column".to_owned(), optional(finding.column.as_ref())),
        (
            "declared_type".to_owned(),
            optional(finding.declared_type.as_ref()),
        ),
        (
            "physical_type".to_owned(),
            optional(finding.physical_type.as_ref()),
        ),
        ("message".to_owned(), text(&finding.message)),
    ])
}

pub(crate) fn resource(resource: &ContractResourceText) -> JsonValue {
    JsonValue::Object(vec![
        ("resource_type".to_owned(), text(&resource.resource_type)),
        ("resource_name".to_owned(), text(&resource.resource_name)),
        ("relation".to_owned(), text(&resource.relation)),
        (
            "findings".to_owned(),
            JsonValue::Array(resource.findings.iter().map(finding).collect()),
        ),
    ])
}
