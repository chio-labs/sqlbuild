use std::collections::HashMap;

use polyglot_sql::expressions::DataType;
use polyglot_sql::traversal::ExpressionWalk;
use polyglot_sql::{DialectType, Expression, ParseOptions, ValidationSchema};

use crate::query_analysis::compatibility_types::{NULL_TYPE, infer_outputs};

/// The output types of the one query in `sql` by full annotation; `None` if a call is untyped.
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
    if has_untyped_call(&expression) {
        return None;
    }
    let mut outputs: Vec<(String, Option<String>)> = Vec::new();
    for (name, data_type) in infer_outputs(&expression, Some(schema), &HashMap::new(), dialect) {
        outputs.push((name, data_type.filter(|value| value != NULL_TYPE)));
    }
    Some(outputs)
}

/// Whether a function call under `node`, outside a typed marker, has no known result type.
fn has_untyped_call(node: &Expression) -> bool {
    match node {
        Expression::Annotated(annotation) if annotation.type_assertion.is_some() => false,
        Expression::Function(_)
        | Expression::AggregateFunction(_)
        | Expression::WindowFunction(_)
            if node.inferred_type().is_none_or(DataType::contains_unknown) =>
        {
            true
        }
        _ => node.children().into_iter().any(has_untyped_call),
    }
}
