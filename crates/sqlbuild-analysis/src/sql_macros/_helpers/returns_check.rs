//! An expression macro's body typed from its declared arguments and checked against `returns`.

use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

use polyglot_sql::ValidationSchema;
use serde_json::{Value, json};

use crate::contracts::_helpers::type_comparison::{TypeComparer, TypeComparison};
use crate::query_analysis::main::output_types::annotated_output_types;
use crate::sql_macros::_helpers::arguments::type_family;
use crate::sql_macros::_helpers::body::expand_body;
use crate::sql_macros::_helpers::typed_calls::typed_sql;
use crate::sql_macros::constants::{
    INFERRED_TEXT_TYPE, RETURNS_MISMATCH_CODE, STAND_IN_RELATION, UNKNOWN_TYPE_HINT, VARCHAR_TYPE,
};
use crate::sql_macros::errors::SqlMacroError;
use crate::sql_macros::models::{
    ArgumentShape, ExpandedText, ParameterKind, RenderedArgument, SqlMacroDefinition, SqlMacroForm,
    SqlMacroLocation, TypeFamily,
};

/// Each body check's verdict, by the probe it ran, so a macro is typed once per process.
static VERDICTS: OnceLock<Mutex<HashMap<String, Option<String>>>> = OnceLock::new();

/// The dialect an adapter's SQL is analysed in.
pub(crate) fn adapter_dialect(adapter: &str) -> &str {
    match adapter {
        "motherduck" => "duckdb",
        "" => "generic",
        other => other,
    }
}

/// The type a parameter's stand-in column has, or `None` for an untyped stand-in.
fn stand_in_type(kind: &ParameterKind) -> Option<&str> {
    match kind {
        ParameterKind::Expression { data_type } | ParameterKind::Constant { data_type } => {
            Some(data_type)
        }
        ParameterKind::Collection { data_type, .. } => Some(data_type),
        ParameterKind::Any
        | ParameterKind::Enum { .. }
        | ParameterKind::Relation { .. }
        | ParameterKind::ColumnOf { .. } => None,
    }
}

/// The name of parameter `index`'s stand-in column.
fn stand_in_column(index: usize) -> String {
    format!("p{index}")
}

/// The body's type with typed stand-ins for its arguments, unless it reads relations or columns.
fn body_probe(definition: &SqlMacroDefinition, body: &ExpandedText) -> Option<(String, Value)> {
    let mut arguments: Vec<RenderedArgument> = Vec::with_capacity(definition.parameters.len());
    let mut columns: Vec<Value> = Vec::with_capacity(definition.parameters.len());
    for (index, parameter) in definition.parameters.iter().enumerate() {
        if matches!(
            parameter.kind,
            ParameterKind::Relation { .. } | ParameterKind::ColumnOf { .. }
        ) {
            return None;
        }
        let column: String = stand_in_column(index);
        let sql: String = match parameter.kind {
            ParameterKind::Collection { .. } => format!("({STAND_IN_RELATION}.{column})"),
            _ => format!("{STAND_IN_RELATION}.{column}"),
        };
        columns.push(json!({
            "name": column,
            "type": stand_in_type(&parameter.kind).unwrap_or(UNKNOWN_TYPE_HINT),
        }));
        arguments.push(RenderedArgument {
            parameter: index,
            sql,
            shape: ArgumentShape::Expression,
            calls: Vec::new(),
        });
    }
    let expansion = expand_body(definition, body, &arguments).ok()?;
    let (typed, _) = typed_sql(&expansion.sql, &expansion.calls);
    let probe: String = format!("SELECT ({typed}) AS b FROM {STAND_IN_RELATION}");
    let table: Value = json!({"name": STAND_IN_RELATION, "columns": columns});
    Some((probe, table))
}

/// The body's inferred type, when inference knows it completely.
fn inferred_body_type(probe: &str, table: Value, dialect: &str) -> Option<String> {
    let schema: ValidationSchema = serde_json::from_value(json!({ "tables": [table] })).ok()?;
    let outputs = annotated_output_types(probe, dialect, &schema)?;
    let (_, data_type) = outputs.into_iter().next()?;
    data_type.filter(|inferred| !inferred.to_ascii_uppercase().contains(UNKNOWN_TYPE_HINT))
}

/// Whether a body of type `inferred` disagrees with `returns`: in another type family, or, for
/// types outside the scalar families, of another type. Within one family the call's own
/// inference decides, since stand-ins lose what literal arguments tell it.
fn disagrees(returns: &str, inferred: &str, adapter: &str) -> bool {
    let (declared, found) = (
        type_family(returns, adapter),
        type_family(inferred, adapter),
    );
    if declared != TypeFamily::Unknown && found != TypeFamily::Unknown {
        return declared != found;
    }
    matches!(
        TypeComparer::new(adapter_dialect(adapter)).types_equal(returns, inferred),
        Ok(TypeComparison::Different)
    )
}

/// Rejects an expression macro whose body's known type is not its declared `returns`.
pub(crate) fn check_body_returns(
    definition: &SqlMacroDefinition,
    body: &ExpandedText,
    (adapter, location): (&str, SqlMacroLocation),
) -> Result<(), SqlMacroError> {
    if definition.form != SqlMacroForm::Expression {
        return Ok(());
    }
    let Some(returns) = definition.returns.as_deref() else {
        return Ok(());
    };
    let Some((probe, table)) = body_probe(definition, body) else {
        return Ok(());
    };
    let dialect: &str = adapter_dialect(adapter);
    let key: String = format!("{dialect}\n{table}\n{probe}");
    let verdicts = VERDICTS.get_or_init(|| Mutex::new(HashMap::new()));
    let known: Option<Option<String>> = verdicts
        .lock()
        .ok()
        .and_then(|verdicts| verdicts.get(&key).cloned());
    let inferred: Option<String> = match known {
        Some(inferred) => inferred,
        None => {
            let inferred: Option<String> = inferred_body_type(&probe, table, dialect);
            if let Ok(mut verdicts) = verdicts.lock() {
                verdicts.insert(key, inferred.clone());
            }
            inferred
        }
    };
    let Some(inferred) = inferred else {
        return Ok(());
    };
    let shown: &str = if inferred.eq_ignore_ascii_case(INFERRED_TEXT_TYPE) {
        VARCHAR_TYPE
    } else {
        &inferred
    };
    if !disagrees(returns, shown, adapter) {
        return Ok(());
    }
    Err(SqlMacroError::new(
        RETURNS_MISMATCH_CODE,
        format!(
            "macro {}() declares returns {returns}, but its body is {shown}",
            definition.name
        ),
    )
    .at(location)
    .helped(format!(
        "declare returns {shown}, CAST the body to {returns}, or remove returns to use the inferred type"
    )))
}
