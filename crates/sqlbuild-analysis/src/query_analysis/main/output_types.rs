use std::collections::HashMap;

use polyglot_sql::{DialectType, Expression, ParseOptions, ValidationSchema};

use crate::query_analysis::compatibility_types::{NULL_TYPE, infer_outputs};

/// The output column names and inferred types of the one query in `sql`, without lineage.
#[must_use]
pub fn output_types(
    sql: &str,
    dialect: &str,
    schema: &ValidationSchema,
) -> Option<Vec<(String, Option<String>)>> {
    let dialect: DialectType = match dialect.parse() {
        Ok(dialect) => dialect,
        Err(_) => return None,
    };
    let mut statements: Vec<Expression> =
        match polyglot_sql::parse_with_options(sql, dialect, &ParseOptions::default()) {
            Ok(statements) => statements,
            Err(_) => return None,
        };
    if statements.len() != 1 {
        return None;
    }
    let expression: Expression = statements.pop()?;
    let mut outputs: Vec<(String, Option<String>)> = Vec::new();
    for (name, data_type) in infer_outputs(&expression, Some(schema), &HashMap::new(), dialect) {
        outputs.push((name, data_type.filter(|value| !is_null_type(value))));
    }
    Some(outputs)
}

/// Whether `value` is the placeholder inference uses for a `NULL` literal's type.
fn is_null_type(value: &str) -> bool {
    value == NULL_TYPE
}
