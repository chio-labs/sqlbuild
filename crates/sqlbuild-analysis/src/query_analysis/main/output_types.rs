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
    let dialect: DialectType = dialect.parse().ok()?;
    let mut statements: Vec<Expression> =
        polyglot_sql::parse_with_options(sql, dialect, &ParseOptions::default()).ok()?;
    if statements.len() != 1 {
        return None;
    }
    let expression: Expression = statements.pop()?;
    let outputs = infer_outputs(&expression, Some(schema), &HashMap::new(), dialect);
    Some(
        outputs
            .into_iter()
            .map(|(name, data_type)| (name, data_type.filter(|value| value != NULL_TYPE)))
            .collect(),
    )
}
