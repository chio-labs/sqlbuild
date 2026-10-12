//! The accessors Python's walk read from the Polyglot wheel, over the crate's own tree.

use polyglot_sql::{Expression, ExpressionWalk};
use serde_json::{Map, Value};

use crate::required_columns::constants::{KIND_ANNOTATED, STAR};

/// The wheel's `kind`.
pub(crate) fn kind(expression: &Expression) -> &'static str {
    expression.variant_name()
}

/// The wheel's `children()`.
pub(crate) fn children(expression: &Expression) -> Vec<&Expression> {
    expression.children()
}

/// The wheel's `alias_or_name`.
pub(crate) fn alias_or_name(expression: &Expression) -> &str {
    let alias: &str = expression.get_alias();
    if alias.is_empty() {
        expression.get_name()
    } else {
        alias
    }
}

/// The wheel's `args`: the serialized payload of the expression's variant.
pub(crate) fn payload(expression: &Expression) -> Map<String, Value> {
    match serde_json::to_value(expression) {
        Ok(Value::Object(map)) => match map.into_iter().next() {
            Some((_, Value::Object(payload))) => payload,
            _ => Map::new(),
        },
        _ => Map::new(),
    }
}

/// The wheel's `is_star`.
pub(crate) fn is_star(expression: &Expression) -> bool {
    match expression {
        Expression::Star(_) => true,
        Expression::Column(column) => column.name.name == STAR,
        _ => false,
    }
}

/// `_unwrap_polyglot_annotations`.
pub(crate) fn unwrap_annotations(expression: &Expression) -> &Expression {
    let mut current: &Expression = expression;
    while kind(current) == KIND_ANNOTATED {
        let Some(inner) = current.get_this() else {
            break;
        };
        current = inner;
    }
    current
}

/// The wheel's `with_ctes()`: each top-level CTE's name, body and whether it aliases columns.
pub(crate) fn top_level_ctes(root: &Expression) -> Vec<(&str, &Expression, bool)> {
    let with = match root {
        Expression::Select(select) => select.with.as_ref(),
        Expression::Union(operation) => operation.with.as_ref(),
        Expression::Intersect(operation) => operation.with.as_ref(),
        Expression::Except(operation) => operation.with.as_ref(),
        _ => None,
    };
    with.map_or_else(Vec::new, |with| {
        with.ctes
            .iter()
            .map(|cte| (cte.alias.name.as_str(), &cte.this, !cte.columns.is_empty()))
            .collect()
    })
}

/// A set operation's `(left, right, by_name)`.
pub(crate) fn set_operation(expression: &Expression) -> Option<(&Expression, &Expression, bool)> {
    match expression {
        Expression::Union(operation) => {
            Some((&operation.left, &operation.right, operation.by_name))
        }
        Expression::Intersect(operation) => {
            Some((&operation.left, &operation.right, operation.by_name))
        }
        Expression::Except(operation) => {
            Some((&operation.left, &operation.right, operation.by_name))
        }
        _ => None,
    }
}
