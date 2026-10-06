//! Relation marker calls in a serialized pre-order walk of a parsed statement's relations.

use polyglot_sql::expressions::{From, Join};
use polyglot_sql::{Expression, ExpressionWalk};

use crate::compiler::_helpers::sql_tests::planning::DBT_REF_FUNCTION;

pub(crate) type MarkerCall = (String, String);

/// Return marker calls in node order, where Polyglot children follow declared field order.
pub(crate) fn relation_marker_calls(expression: &Expression) -> Vec<MarkerCall> {
    expression.dfs().flat_map(node_marker_calls).collect()
}

/// FROM then JOIN marker calls of one node, plus the serialized `on` that traversal skips.
fn node_marker_calls(node: &Expression) -> Vec<MarkerCall> {
    match node {
        Expression::Select(select) => select
            .from
            .iter()
            .flat_map(from_markers)
            .chain(join_markers(&select.joins))
            .collect(),
        Expression::From(from) => from_markers(from).collect(),
        Expression::Delete(delete) => join_markers(&delete.joins).collect(),
        Expression::JoinedTable(table) => join_markers(&table.joins).collect(),
        Expression::DataDeletionProperty(property) => relation_marker_calls(&property.on),
        _ => Vec::new(),
    }
}

fn from_markers(from: &From) -> impl Iterator<Item = MarkerCall> + '_ {
    from.expressions.iter().filter_map(marker)
}

fn join_markers(joins: &[Join]) -> impl Iterator<Item = MarkerCall> + '_ {
    joins.iter().filter_map(|join| marker(&join.this))
}

fn marker(expression: &Expression) -> Option<MarkerCall> {
    match expression {
        Expression::Alias(alias) => marker(&alias.this),
        Expression::Function(function) => {
            let names: Vec<Option<&str>> = function
                .args
                .iter()
                .map(|argument| match argument {
                    Expression::Column(column) => Some(column.name.name.as_str()),
                    _ => None,
                })
                .collect();
            function_marker(&function.name, &names)
        }
        _ => None,
    }
}

fn function_marker(name: &str, args: &[Option<&str>]) -> Option<MarkerCall> {
    let function_name = name.to_ascii_lowercase();
    let referenced_name = if function_name == DBT_REF_FUNCTION {
        match args {
            [Some(first)] => (*first).to_string(),
            [Some(first), Some(second)] => format!("{first}__{second}"),
            _ => return None,
        }
    } else {
        let [Some(first)] = args else {
            return None;
        };
        (*first).to_string()
    };
    Some((function_name, referenced_name))
}
