//! Layout-independent text of a SQL macro's header parts.

use crate::definition_changes::main::sql_definition_digest::sql_definition_digest;
use crate::sql_macros::models::{ParameterKind, SqlMacroParameter};

/// A parameter's name, kind, types and default, independent of how the header was laid out.
pub(crate) fn parameter_text(parameter: &SqlMacroParameter) -> String {
    let kind: String = match &parameter.kind {
        ParameterKind::Expression { data_type } => format!("expression {}", type_text(data_type)),
        ParameterKind::Any { family: None } => "expression any".to_owned(),
        ParameterKind::Any {
            family: Some(family),
        } => format!("expression any {}", family.keyword().to_lowercase()),
        ParameterKind::Constant { data_type } => format!("const {}", type_text(data_type)),
        ParameterKind::Collection { set, data_type } => {
            format!("collection {set} {}", type_text(data_type))
        }
        ParameterKind::Enum { name } => format!("enum {}", name.to_lowercase()),
        ParameterKind::Relation { columns } => relation_text(columns),
        ParameterKind::ColumnOf { relation } => format!("column of {}", relation.to_lowercase()),
    };
    let default: String = parameter
        .default
        .as_deref()
        .map(sql_definition_digest)
        .unwrap_or_default();
    format!("{} {kind} {default}", parameter.name.to_lowercase())
}

/// A relation parameter's required columns and their types.
fn relation_text(columns: &[(String, String)]) -> String {
    let mut text: String = String::from("relation");
    for (column, data_type) in columns {
        text.push_str(&format!(
            " {} {}",
            column.to_lowercase(),
            type_text(data_type)
        ));
    }
    text
}

/// A SQL type with case and spacing ignored.
pub(crate) fn type_text(data_type: &str) -> String {
    data_type
        .split_whitespace()
        .collect::<String>()
        .to_uppercase()
}
