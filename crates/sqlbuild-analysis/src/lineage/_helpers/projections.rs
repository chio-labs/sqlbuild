//! Python's fast lineage reads of wheel expression accessors, over the same crate expressions.

use std::collections::{HashMap, HashSet};

use polyglot_sql::{Expression, ExpressionWalk, ast_json};
use serde_json::Value;

use crate::lineage::_helpers::python_payload::{PythonValue, python_payload};
use crate::lineage::_helpers::references::PhysicalResource;
use crate::lineage::constants::{
    AGGREGATE_KINDS, CAST_KINDS, KIND_ALIAS, KIND_COLUMN, KIND_SELECT, KIND_TABLE, PAYLOAD_COLUMN,
    PAYLOAD_NAME, PAYLOAD_TABLE, SET_OPERATION_KINDS, SET_OPERATION_SIDES, STAR_COLUMN_NAME,
};
use crate::lineage::models::{
    LineageConfidence, LineageResourceType, LineageSource, LineageTransformKind,
};

/// Payload nesting past which Python's recursive `to_dict` walk may exceed its recursion limit.
const MAX_PAYLOAD_DEPTH: usize = 400;

/// A read Python would make differently, or fail on, so the model is deferred to Python.
#[derive(Debug)]
pub(crate) struct UnreadableExpression;

/// Table names and aliases mapped to resources, in Python's dictionary insertion order.
pub(crate) struct AliasMap<'a> {
    entries: Vec<(String, &'a PhysicalResource)>,
}

impl<'a> AliasMap<'a> {
    fn insert(&mut self, key: &str, resource: &'a PhysicalResource) {
        match self.entries.iter_mut().find(|(name, _)| name == key) {
            Some(entry) => entry.1 = resource,
            None => self.entries.push((key.to_owned(), resource)),
        }
    }

    fn get(&self, key: &str) -> Option<&'a PhysicalResource> {
        self.entries
            .iter()
            .find(|(name, _)| name == key)
            .map(|(_, resource)| *resource)
    }

    /// Python's `_single_alias_resource`: the one resource every entry names, by resource name.
    pub(crate) fn single_resource(&self) -> Option<&'a PhysicalResource> {
        let mut values = self.entries.iter().map(|(_, resource)| *resource);
        let first = values.next()?;
        values
            .all(|candidate| candidate.resource_name == first.resource_name)
            .then_some(first)
    }
}

pub(crate) fn is_star(expression: &Expression) -> bool {
    match expression {
        Expression::Star(_) => true,
        Expression::Column(column) => column.name.name == STAR_COLUMN_NAME,
        _ => false,
    }
}

/// `projection.this` for an alias, the projection itself otherwise.
pub(crate) fn unaliased(projection: &Expression) -> Result<&Expression, UnreadableExpression> {
    if projection.variant_name() == KIND_ALIAS {
        return projection.get_this().ok_or(UnreadableExpression);
    }
    Ok(projection)
}

/// Python's `_polyglot_projection_output_name`.
pub(crate) fn projection_output_name(
    projection: &Expression,
    index: usize,
    inferred_names: &[String],
) -> Option<String> {
    let output_name = projection.get_output_name();
    if !output_name.is_empty() && output_name != STAR_COLUMN_NAME {
        return Some(output_name.to_owned());
    }
    let alias = projection.get_alias();
    let alias_or_name = if alias.is_empty() {
        projection.get_name()
    } else {
        alias
    };
    if !alias_or_name.is_empty() && alias_or_name != STAR_COLUMN_NAME {
        return Some(alias_or_name.to_owned());
    }
    inferred_names.get(index).cloned()
}

/// Python's `_polyglot_table_alias_map` over `find_all("table")`.
pub(crate) fn table_alias_map<'a>(
    expression: &Expression,
    physical_resources: &'a [PhysicalResource],
) -> AliasMap<'a> {
    let mut by_name: HashMap<&str, &'a PhysicalResource> = HashMap::new();
    for resource in physical_resources {
        let _ = by_name.insert(resource.physical_name.as_str(), resource);
    }
    for resource in physical_resources {
        let _ = by_name.insert(resource.resource_name.as_str(), resource);
    }
    let mut alias_map = AliasMap {
        entries: Vec::new(),
    };
    for table in expression
        .dfs()
        .skip(1)
        .filter(|node| node.variant_name() == KIND_TABLE)
    {
        let table_name = table.get_name();
        let Some(resource) = by_name.get(table_name) else {
            continue;
        };
        alias_map.insert(table_name, resource);
        let alias = table.get_alias();
        let alias_or_name = if alias.is_empty() { table_name } else { alias };
        if !alias_or_name.is_empty() {
            alias_map.insert(alias_or_name, resource);
        }
    }
    alias_map
}

/// Python's `_polyglot_projection_upstream_columns`.
pub(crate) fn projection_upstream_columns(
    projection: &Expression,
    alias_map: &AliasMap<'_>,
    unqualified_resource: Option<&PhysicalResource>,
) -> Result<(Vec<LineageSource>, LineageConfidence), UnreadableExpression> {
    let mut columns: Vec<LineageSource> = Vec::new();
    let mut seen: HashSet<(LineageResourceType, String, String)> = HashSet::new();
    let mut confidence = LineageConfidence::High;
    for (column_name, table_name) in column_refs(projection)? {
        if column_name.is_empty() {
            continue;
        }
        let resource = if !table_name.is_empty() {
            alias_map.get(&table_name)
        } else if let Some(resource) = unqualified_resource {
            confidence = LineageConfidence::Medium;
            Some(resource)
        } else {
            confidence = LineageConfidence::Unknown;
            None
        };
        let Some(resource) = resource else {
            continue;
        };
        let key = (
            resource.resource_type,
            resource.resource_name.clone(),
            column_name,
        );
        if seen.contains(&key) {
            continue;
        }
        columns.push(LineageSource {
            resource_type: key.0,
            resource_name: key.1.clone(),
            column_name: key.2.clone(),
        });
        let _ = seen.insert(key);
    }
    Ok((columns, confidence))
}

/// Python's `_polyglot_classify_transform`.
pub(crate) fn classify_transform(
    expression: &Expression,
    upstream_columns: &[LineageSource],
) -> LineageTransformKind {
    let kind = expression.variant_name();
    if is_star(expression) {
        return LineageTransformKind::Star;
    }
    if CAST_KINDS.contains(&kind) {
        return LineageTransformKind::Cast;
    }
    if expression
        .dfs()
        .any(|node| AGGREGATE_KINDS.contains(&node.variant_name()))
    {
        return LineageTransformKind::Aggregation;
    }
    if upstream_columns.is_empty() {
        return LineageTransformKind::Constant;
    }
    if kind == KIND_COLUMN && upstream_columns.len() == 1 {
        return LineageTransformKind::Direct;
    }
    LineageTransformKind::Expression
}

/// Python's `_polyglot_set_expression_selects`, reading set-operation sides through `args`.
pub(crate) fn set_expression_selects(
    expression: Expression,
) -> Result<Vec<Expression>, UnreadableExpression> {
    let kind = expression.variant_name();
    if kind == KIND_SELECT {
        return Ok(vec![expression]);
    }
    let mut selects: Vec<Expression> = Vec::new();
    if !SET_OPERATION_KINDS.contains(&kind) {
        return Ok(selects);
    }
    let payload = serde_json::to_value(&expression).map_err(|_| UnreadableExpression)?;
    let Some(Value::Object(arguments)) = payload_arguments(payload) else {
        return Ok(selects);
    };
    for side in SET_OPERATION_SIDES {
        let Some(value) = arguments.get(side) else {
            continue;
        };
        if let Ok(child) = ast_json::expression_from_value(value.clone()) {
            selects.extend(set_expression_selects(child)?);
        }
    }
    Ok(selects)
}

/// The wheel's `args`: the payload under an expression's single variant key.
fn payload_arguments(payload: Value) -> Option<Value> {
    match payload {
        Value::Object(map) => map.into_iter().next().map(|(_, value)| value),
        _ => None,
    }
}

/// Python's `_polyglot_column_refs_in_expression`: `(column, table)` pairs in payload order.
fn column_refs(expression: &Expression) -> Result<Vec<(String, String)>, UnreadableExpression> {
    let payload: PythonValue = python_payload(expression).map_err(|_| UnreadableExpression)?;
    if expression.variant_name() == KIND_COLUMN {
        let table = payload
            .get(PAYLOAD_COLUMN)
            .and_then(|column| column.get(PAYLOAD_TABLE));
        let table_name = match table.and_then(|table| table.get(PAYLOAD_NAME)) {
            Some(PythonValue::Str(name)) => name.clone(),
            _ => String::new(),
        };
        return Ok(vec![(expression.get_name().to_owned(), table_name)]);
    }
    payload_column_refs(&payload, 0)
}

/// Python's recursive `visit`: a `column` dict ends its branch; tuples are never entered.
fn payload_column_refs(
    node: &PythonValue,
    depth: usize,
) -> Result<Vec<(String, String)>, UnreadableExpression> {
    if depth > MAX_PAYLOAD_DEPTH {
        return Err(UnreadableExpression);
    }
    let children: Vec<&PythonValue> = match node {
        PythonValue::Dict(entries) => {
            if let Some(column @ PythonValue::Dict(_)) = node.get(PAYLOAD_COLUMN) {
                let table_name = match column.get(PAYLOAD_TABLE) {
                    Some(table @ PythonValue::Dict(_)) => {
                        name_payload_value(table.get(PAYLOAD_NAME))
                    }
                    _ => String::new(),
                };
                return Ok(vec![(
                    name_payload_value(column.get(PAYLOAD_NAME)),
                    table_name,
                )]);
            }
            entries.iter().map(|(_, value)| value).collect()
        }
        PythonValue::List(values) => values.iter().collect(),
        _ => Vec::new(),
    };
    let mut refs: Vec<(String, String)> = Vec::new();
    for child in children {
        refs.extend(payload_column_refs(child, depth + 1)?);
    }
    Ok(refs)
}

/// Python's `_polyglot_name_payload_value`.
fn name_payload_value(payload: Option<&PythonValue>) -> String {
    match payload {
        Some(PythonValue::Str(name)) => name.clone(),
        Some(map @ PythonValue::Dict(_)) => match map.get(PAYLOAD_NAME) {
            Some(PythonValue::Str(name)) => name.clone(),
            _ => String::new(),
        },
        _ => String::new(),
    }
}
