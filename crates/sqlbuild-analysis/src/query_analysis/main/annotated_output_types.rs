use std::collections::HashMap;

use polyglot_sql::{DialectType, Expression, ParseOptions, ValidationSchema};

use crate::query_analysis::compatibility_types::{NULL_TYPE, infer_outputs};

/// The output columns and types of the one query in `sql`, typed by full type annotation.
#[must_use]
pub fn annotated_output_types(
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
    let mut expression: Expression = statements.pop()?;
    let mapping = polyglot_sql::validation::mapping_schema_from_validation_schema_with_dialect(
        schema, dialect,
    );
    polyglot_sql::optimizer::annotate_types::annotate_types(
        &mut expression,
        Some(&mapping as &dyn polyglot_sql::schema::Schema),
        Some(dialect),
    );
    let mut outputs: Vec<(String, Option<String>)> = Vec::new();
    for (name, data_type) in infer_outputs(&expression, Some(schema), &HashMap::new(), dialect) {
        outputs.push((name, data_type.filter(|value| value != NULL_TYPE)));
    }
    Some(outputs)
}
