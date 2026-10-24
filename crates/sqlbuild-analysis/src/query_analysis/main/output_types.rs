use std::collections::HashMap;

use polyglot_sql::{DialectType, Expression, ParseOptions, ValidationSchema};

use crate::query_analysis::compatibility_types::{
    NULL_TYPE, infer_complete_outputs, infer_outputs,
};

/// The output columns and inferred types of the one query in `sql`; `None` if a source is untyped.
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
    let inferred = infer_complete_outputs(&expression, Some(schema), &HashMap::new(), dialect)?;
    for (name, data_type) in inferred {
        outputs.push((name, data_type.filter(|value| !is_null_type(value))));
    }
    Some(outputs)
}

/// The output columns and types of the one query in `sql`, typed by full type annotation.
#[must_use]
pub fn annotated_output_types(
    sql: &str,
    dialect: &str,
    schema: &ValidationSchema,
) -> Option<Vec<(String, Option<String>)>> {
    let dialect: DialectType = dialect.parse().ok()?;
    let mut statements: Vec<Expression> =
        polyglot_sql::parse_with_options(sql, dialect, &ParseOptions::default()).ok()?;
    if statements.len() != 1 {
        return None;
    }
    let mut expression: Expression = statements.pop()?;
    let mapping = polyglot_sql::validation::mapping_schema_from_validation_schema_with_dialect(
        schema, dialect,
    );
    polyglot_sql::optimizer::annotate_types::annotate_types(
        &mut expression,
        Some(&mapping as &dyn polyglot_sql::schema::Schema),
        Some(dialect),
    );
    Some(
        infer_outputs(&expression, Some(schema), &HashMap::new(), dialect)
            .into_iter()
            .map(|(name, data_type)| (name, data_type.filter(|value| !is_null_type(value))))
            .collect(),
    )
}

/// Whether `value` is the placeholder inference uses for a `NULL` literal's type.
fn is_null_type(value: &str) -> bool {
    value == NULL_TYPE
}
