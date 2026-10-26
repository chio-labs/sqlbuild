//! String literals that fill an enum-typed output column but are not members of the enum.

use crate::contracts::_helpers::enum_literals::{literal_location, output_literals, parsed_query};
use crate::contracts::constants::{CASE_INSENSITIVE_DIALECTS, ENUM_LITERAL_CODE};
use crate::contracts::models::{EnumColumn, EnumLiteralModel, EnumLiteralViolation};

/// One violation per column and distinct constant literal, in column order and then query order.
#[must_use]
pub fn enum_literal_violations(model: &EnumLiteralModel<'_>) -> Vec<EnumLiteralViolation> {
    if model.columns.is_empty() || CASE_INSENSITIVE_DIALECTS.contains(&model.dialect) {
        return Vec::new();
    }
    let Some(query) = parsed_query(model.query_sql, model.dialect) else {
        return Vec::new();
    };
    let mut violations: Vec<EnumLiteralViolation> = Vec::new();
    for column in &model.columns {
        let mut reported: Vec<String> = Vec::new();
        for value in output_literals(&query, &column.name) {
            if column.members.contains(&value) || reported.contains(&value) {
                continue;
            }
            violations.push(violation(model, column, &value));
            reported.push(value);
        }
    }
    violations
}

fn violation(
    model: &EnumLiteralModel<'_>,
    column: &EnumColumn,
    value: &str,
) -> EnumLiteralViolation {
    let members: Vec<String> = column.members.iter().map(|member| quoted(member)).collect();
    EnumLiteralViolation {
        code: ENUM_LITERAL_CODE,
        column_name: column.name.clone(),
        value: value.to_owned(),
        message: format!(
            "value {} in column '{}' of model '{}' is not a member of enum {}",
            quoted(value),
            column.name,
            model.name,
            column.enum_name
        ),
        help: format!(
            "add {} to enum {} or use one of its members: {}",
            quoted(value),
            column.enum_name,
            members.join(", ")
        ),
        location: literal_location(
            (model.authored_sql, model.authored_query_sql),
            value,
            model.dialect,
        ),
    }
}

/// `value` as a SQL string literal.
fn quoted(value: &str) -> String {
    format!("'{}'", value.replace('\'', "''"))
}
