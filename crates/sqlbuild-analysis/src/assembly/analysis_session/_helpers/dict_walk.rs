//! Python's view of a parsed query: the wheel's expression accessors and its dict walk.

use polyglot_sql::expressions::Cte;
use polyglot_sql::traversal::ExpressionWalk;
use polyglot_sql::{ComplexityGuardOptions, Dialect, Expression, ParseOptions, ast_json};
use serde_json::{Map, Value, json};
use sqlbuild_core::text::main::active_python_text::active_python_text;
use sqlbuild_core::text::main::python_casefold::python_casefold;
use sqlbuild_core::text::main::python_upper::python_upper;

use crate::assembly::analysis_session::constants::{
    ALIAS_AST_KIND, ANNOTATED_AST_KIND, COLUMN_AST_KIND, DEPENDENCY_FUNCTION_NAMES,
    FUNCTION_AST_KIND, MAX_FUNCTION_CALL_DEPTH, RENDERED_TYPE_NAMES, STAR_AST_KIND, TABLE_AST_KIND,
    WILDCARD,
};

/// Python's `bool(value)`.
pub(crate) fn truthy(value: Option<&Value>) -> bool {
    match value {
        Some(Value::Bool(flag)) => *flag,
        Some(Value::Null) | None => false,
        Some(Value::String(text)) => !text.is_empty(),
        Some(Value::Array(items)) => !items.is_empty(),
        Some(Value::Object(items)) => !items.is_empty(),
        Some(Value::Number(number)) => number.as_f64() != Some(0.0),
    }
}

/// The single key of a one-key object, or "" for anything else.
pub(crate) fn node_key(node: Option<&Value>) -> &str {
    let Some(object) = node
        .and_then(Value::as_object)
        .filter(|object| object.len() == 1)
    else {
        return "";
    };
    object.keys().next().map_or("", String::as_str)
}

/// The payload under a node's single key.
pub(crate) fn payload(node: Option<&Value>) -> Option<&Map<String, Value>> {
    let key: &str = node_key(node);
    node.and_then(|node| node.get(key))
        .and_then(Value::as_object)
}

/// Python's `_dict_list`: the objects of a list, or nothing.
pub(crate) fn dict_list(value: Option<&Value>) -> Vec<&Value> {
    match value.and_then(Value::as_array) {
        Some(items) => objects(items),
        None => Vec::new(),
    }
}

fn objects(items: &[Value]) -> Vec<&Value> {
    items.iter().filter(|item| item.is_object()).collect()
}

/// Python's `_nested`: follow object keys.
pub(crate) fn nested<'a>(node: Option<&'a Value>, keys: &[&str]) -> Option<&'a Value> {
    let mut current: Option<&Value> = node;
    for key in keys {
        current = current
            .and_then(Value::as_object)
            .and_then(|object| object.get(*key));
    }
    current
}

/// Python's `_identifier_name`.
pub(crate) fn identifier_name(node: Option<&Value>) -> Option<&str> {
    match node {
        Some(Value::String(name)) => Some(name),
        Some(Value::Object(object)) => object
            .get("name")
            .and_then(Value::as_str)
            .filter(|name| !name.is_empty()),
        _ => None,
    }
}

/// Python's `_column_name`.
pub(crate) fn column_name(node: Option<&Value>) -> Option<&str> {
    if node_key(node) != COLUMN_AST_KIND {
        return None;
    }
    identifier_name(payload(node)?.get("name"))
}

/// Python's `_relation_name`: a table, a column or a dependency call's first argument.
pub(crate) fn relation_name(node: Option<&Value>) -> Option<&str> {
    let key: &str = node_key(node);
    let payload: &Map<String, Value> = payload(node)?;
    if key == TABLE_AST_KIND || key == COLUMN_AST_KIND {
        return identifier_name(payload.get("name"));
    }
    let called: &str = payload
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if key == FUNCTION_AST_KIND && DEPENDENCY_FUNCTION_NAMES.contains(&casefold(called).as_str()) {
        return column_name(dict_list(payload.get("args")).first().copied());
    }
    None
}

/// Python's `_is_single_wildcard`.
pub(crate) fn is_single_wildcard(value: Option<&Value>) -> bool {
    let expressions: Vec<&Value> = dict_list(value);
    let [only] = expressions.as_slice() else {
        return false;
    };
    if node_key(Some(only)) != STAR_AST_KIND {
        return false;
    }
    let Some(star) = only.get(STAR_AST_KIND).and_then(Value::as_object) else {
        return false;
    };
    !["except", "replace", "rename", "table"]
        .iter()
        .any(|key| truthy(star.get(*key)))
}

/// Python's `_render_type` of a cast target.
pub(crate) fn render_type(node: Option<&Value>) -> Option<String> {
    let node: &Map<String, Value> = node?.as_object()?;
    let raw_type: &str = node
        .get("data_type")
        .and_then(Value::as_str)
        .filter(|raw| !raw.is_empty())?;
    let folded: String = casefold(raw_type);
    let rendered: String = RENDERED_TYPE_NAMES
        .iter()
        .find(|(name, _)| *name == folded)
        .map_or_else(
            || upper(&raw_type.replace('_', " ")),
            |(_, rendered)| (*rendered).to_owned(),
        );
    if let Some(length) = python_int(node.get("length")) {
        return Some(format!("{rendered}({length})"));
    }
    let Some(precision) = python_int(node.get("precision")) else {
        return Some(rendered);
    };
    Some(match python_int(node.get("scale")) {
        Some(scale) => format!("{rendered}({precision}, {scale})"),
        None => format!("{rendered}({precision})"),
    })
}

/// Python's `str(value)` for a value `isinstance(value, int)` accepts.
pub(crate) fn python_int(value: Option<&Value>) -> Option<String> {
    match value? {
        Value::Bool(flag) => Some(if *flag { "True" } else { "False" }.to_owned()),
        Value::Number(number) if number.is_i64() || number.is_u64() => Some(number.to_string()),
        _ => None,
    }
}

/// Python's `str.casefold`.
pub(crate) fn casefold(text: &str) -> String {
    python_casefold(active_python_text(), text)
}

/// Python's `str.upper`.
pub(crate) fn upper(text: &str) -> String {
    python_upper(active_python_text(), text)
}

/// A value the wheel hands Python for one payload key: an expression, a list of them, or data.
#[derive(Debug, Clone)]
pub(crate) enum PyValue {
    Expr(Expression),
    Exprs(Vec<Expression>),
    Raw(Value),
}

/// The wheel's guarded `parse_one`; Ok(None) is the `PolyglotError` Python catches.
pub(crate) fn parse_one(sql: &str, dialect: &str) -> Result<Option<Expression>, String> {
    Ok(parse_one_or_error(sql, dialect)?.ok())
}

/// The wheel's guarded `parse_one`, with the message of the `PolyglotError` it raises.
pub(crate) fn parse_one_or_error(
    sql: &str,
    dialect: &str,
) -> Result<Result<Expression, String>, String> {
    let guard: ComplexityGuardOptions =
        serde_json::from_value(json!({"maxFunctionCallDepth": MAX_FUNCTION_CALL_DEPTH}))
            .map_err(|error| error.to_string())?;
    let options: ParseOptions = ParseOptions {
        complexity_guard: Some(guard),
    };
    let parsed: Result<Vec<Expression>, _> = Dialect::get_by_name(dialect)
        .ok_or_else(|| format!("unknown dialect {dialect}"))?
        .parse_with_options(sql, &options);
    let mut expressions: Vec<Expression> = match parsed {
        Ok(expressions) => expressions,
        Err(error) => return Ok(Err(error.to_string())),
    };
    if expressions.len() != 1 {
        return Ok(Err(format!(
            "Expected 1 statement, found {}",
            expressions.len()
        )));
    }
    Ok(expressions.pop().ok_or_else(|| "no statement".to_owned()))
}

/// `str(getattr(node, "kind", ""))`.
pub(crate) fn kind(node: Option<&Expression>) -> &'static str {
    node.map_or("", Expression::variant_name)
}

/// `node.name`, "" for None.
pub(crate) fn name(node: Option<&Expression>) -> &str {
    node.map_or("", Expression::get_name)
}

/// `node.output_name`, "" for None.
pub(crate) fn output_name(node: Option<&Expression>) -> &str {
    node.map_or("", Expression::get_output_name)
}

/// `node.alias_or_name`.
pub(crate) fn alias_or_name(node: &Expression) -> &str {
    let alias: &str = node.get_alias();
    if alias.is_empty() {
        node.get_name()
    } else {
        alias
    }
}

/// `node.is_star`.
pub(crate) fn is_star(node: Option<&Expression>) -> bool {
    match node {
        Some(Expression::Star(_)) => true,
        Some(Expression::Column(column)) => column.name.name == WILDCARD,
        _ => false,
    }
}

/// Python's `_unwrap_polyglot_annotations`.
pub(crate) fn unwrap_annotations(mut node: Option<&Expression>) -> Option<&Expression> {
    while kind(node) == ANNOTATED_AST_KIND {
        node = node.and_then(Expression::get_this);
    }
    node
}

/// A projection's expression: an alias's `this`, otherwise the projection.
pub(crate) fn projected_expression(projection: Option<&Expression>) -> Option<&Expression> {
    if kind(projection) == ALIAS_AST_KIND {
        return projection.and_then(Expression::get_this);
    }
    projection
}

/// `node.this` then `node.expressions`: Python's `_polyglot_expression_args`.
pub(crate) fn expression_args(node: Option<&Expression>) -> Vec<&Expression> {
    let Some(node) = node else {
        return Vec::new();
    };
    node.get_this()
        .into_iter()
        .chain(node.get_expressions())
        .collect()
}

/// `node.children()`.
pub(crate) fn children(node: &Expression) -> Vec<&Expression> {
    ExpressionWalk::children(node)
}

/// Python's `_polyglot_direct_select_tables`: the table children.
pub(crate) fn direct_tables(node: &Expression) -> Vec<&Expression> {
    children(node)
        .into_iter()
        .filter(|child| child.variant_name() == TABLE_AST_KIND)
        .collect()
}

/// `node.find_all(kind)`: descendants in depth-first order, the node itself excluded.
pub(crate) fn find_all<'a>(node: &'a Expression, wanted: &str) -> Vec<&'a Expression> {
    node.dfs()
        .skip(1)
        .filter(|descendant| descendant.variant_name() == wanted)
        .collect()
}

/// `node.to_dict()`.
pub(crate) fn to_dict(node: &Expression) -> Result<Value, String> {
    serde_json::to_value(node).map_err(|error| error.to_string())
}

/// The wheel's `expression_payload`: the tagged value's fields.
pub(crate) fn expression_payload(node: &Expression) -> Result<Map<String, Value>, String> {
    Ok(match to_dict(node)? {
        Value::Object(map) => match map.into_iter().next() {
            Some((_, Value::Object(payload))) => payload,
            _ => Map::new(),
        },
        _ => Map::new(),
    })
}

/// `node.args.get(key)` (and `node.arg(key)` outside its special keys); None for Python's None.
pub(crate) fn arg(node: Option<&Expression>, key: &str) -> Result<Option<PyValue>, String> {
    let Some(node) = node else {
        return Ok(None);
    };
    Ok(expression_payload(node)?.remove(key).and_then(py_value))
}

/// The wheel's `value_to_python_object`; None where Python sees None.
fn py_value(value: Value) -> Option<PyValue> {
    if let Ok(expression) = ast_json::expression_from_value(value.clone()) {
        return Some(PyValue::Expr(expression));
    }
    if let Ok(expressions) = ast_json::expressions_from_value(value.clone()) {
        return Some(PyValue::Exprs(expressions));
    }
    (!value.is_null()).then_some(PyValue::Raw(value))
}

/// Python's `bool()` of a converted value: expressions are always truthy.
pub(crate) fn py_truthy(value: Option<&PyValue>) -> bool {
    match value {
        None => false,
        Some(PyValue::Expr(_)) => true,
        Some(PyValue::Exprs(items)) => !items.is_empty(),
        Some(PyValue::Raw(raw)) => truthy(Some(raw)),
    }
}

/// Python's `_polyglot_name_payload_value` of a converted value.
pub(crate) fn name_payload(value: Option<&PyValue>) -> String {
    match value {
        Some(PyValue::Raw(raw)) => raw_name_payload(Some(raw)),
        _ => String::new(),
    }
}

/// Python's `_polyglot_name_payload_value` of plain data.
pub(crate) fn raw_name_payload(value: Option<&Value>) -> String {
    match value {
        Some(Value::String(text)) => text.clone(),
        Some(Value::Object(object)) => object
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned(),
        _ => String::new(),
    }
}

/// Python's `_polyglot_column_table_name`: `to_dict()["column"]["table"]["name"]`.
pub(crate) fn column_table_name(node: &Expression) -> Result<String, String> {
    let value: Value = to_dict(node)?;
    let table: Option<&Value> = value
        .get("column")
        .filter(|column| column.is_object())
        .and_then(|column| column.get("table"))
        .filter(|table| table.is_object());
    Ok(raw_name_payload(table))
}

/// The top-level CTEs `with_ctes()` returns: name, whether it has column aliases, and its body.
pub(crate) fn top_level_ctes(node: &Expression) -> Vec<(&str, bool, &Expression)> {
    let with = match node {
        Expression::Select(select) => select.with.as_ref(),
        Expression::Union(union) => union.with.as_ref(),
        Expression::Intersect(intersect) => intersect.with.as_ref(),
        Expression::Except(except) => except.with.as_ref(),
        _ => None,
    };
    with.map(|with| with.ctes.iter().map(cte_entry).collect())
        .unwrap_or_default()
}

fn cte_entry(cte: &Cte) -> (&str, bool, &Expression) {
    (cte.alias.name.as_str(), !cte.columns.is_empty(), &cte.this)
}

/// A set operation's `arg("left")`, `arg("right")` and `arg("by_name")`.
pub(crate) fn set_operation(node: &Expression) -> Option<(&Expression, &Expression, bool)> {
    match node {
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

/// A select's `arg("where_clause")` as plain data.
pub(crate) fn where_clause(node: &Expression) -> Result<Option<Value>, String> {
    let Expression::Select(select) = node else {
        return Ok(None);
    };
    select
        .where_clause
        .as_ref()
        .map(|clause| serde_json::to_value(clause).map_err(|error| error.to_string()))
        .transpose()
}
