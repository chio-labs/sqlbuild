use std::collections::HashMap;

use polyglot_sql::expressions::DataType;
use polyglot_sql::{DialectType, Expression, ParseOptions, ValidationSchema};

use crate::query_analysis::annotated_types::{has_untyped_call, projection_types};
use crate::query_analysis::compatibility_types::{NULL_TYPE, infer_outputs};
use crate::query_analysis::types::AnnotatedOutput;

/// Each output of the one query in `sql`, typed by full annotation; `None` if a call is untyped.
#[must_use]
pub fn annotated_output_types(
    sql: &str,
    dialect: &str,
    schema: &ValidationSchema,
) -> Option<Vec<AnnotatedOutput>> {
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
    if has_untyped_call(&expression, dialect) {
        return None;
    }
    let annotated: Vec<Option<DataType>> = projection_types(&expression);
    let mut outputs: Vec<AnnotatedOutput> = Vec::new();
    for (index, (name, data_type)) in
        infer_outputs(&expression, Some(schema), &HashMap::new(), dialect)
            .into_iter()
            .enumerate()
    {
        outputs.push((
            name,
            data_type.filter(|value| value != NULL_TYPE),
            annotated.get(index).cloned().flatten(),
        ));
    }
    Some(outputs)
}
