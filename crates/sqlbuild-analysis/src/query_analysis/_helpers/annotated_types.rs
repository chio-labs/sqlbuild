//! Facts of a fully annotated query: which calls annotation could not type, and output types.

use polyglot_sql::expressions::DataType;
use polyglot_sql::optimizer::annotate_types::function_result_is_known;
use polyglot_sql::traversal::ExpressionWalk;
use polyglot_sql::{DialectType, Expression};

/// Whether a call under `node`, outside a typed marker, has an unknown or only guessed type.
pub(crate) fn has_untyped_call(node: &Expression, dialect: DialectType) -> bool {
    match node {
        Expression::Annotated(annotation) if annotation.type_assertion.is_some() => false,
        Expression::Function(function)
            if !function_result_is_known(function, dialect) || is_unknown(node) =>
        {
            true
        }
        Expression::AggregateFunction(_) | Expression::WindowFunction(_) if is_unknown(node) => {
            true
        }
        _ => node
            .children()
            .into_iter()
            .any(|child| has_untyped_call(child, dialect)),
    }
}

/// Whether annotation left `node` without a type, or with a wholly unknown one.
fn is_unknown(node: &Expression) -> bool {
    node.inferred_type()
        .is_none_or(|data_type| *data_type == DataType::Unknown)
}

/// The annotated type of each projection of a `SELECT`, past its alias.
pub(crate) fn projection_types(expression: &Expression) -> Vec<Option<DataType>> {
    let Expression::Select(select) = expression else {
        return Vec::new();
    };
    let mut types: Vec<Option<DataType>> = Vec::with_capacity(select.expressions.len());
    for projection in &select.expressions {
        let value: &Expression = match projection {
            Expression::Alias(alias) => &alias.this,
            other => other,
        };
        types.push(value.inferred_type().cloned());
    }
    types
}
