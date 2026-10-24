//! An expression macro's body typed from its declared arguments and checked against `returns`.

use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

use polyglot_sql::{DialectType, SchemaValidationOptions, ValidationSchema, validate_with_schema};
use serde_json::{Value, json};

use crate::contracts::_helpers::type_comparison::{TypeComparer, TypeComparison};
use crate::query_analysis::main::output_types::annotated_output_types;
use crate::sql_macros::_helpers::arguments::type_family;
use crate::sql_macros::_helpers::body::expand_body;
use crate::sql_macros::_helpers::typed_calls::typed_sql;
use crate::sql_macros::constants::{
    BODY_TYPE_CODE, INFERRED_TEXT_TYPE, RETURNS_MISMATCH_CODE, STAND_IN_RELATION, TYPE_ERROR_CODES,
    TYPE_WARNING_CODES, UNKNOWN_TYPE_HINT, VARCHAR_TYPE,
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

/// The type a parameter's stand-in column has, or `None` for an untyped stand-in; an `ANY`
/// family takes its widest member when `families` is set.
fn stand_in_type(kind: &ParameterKind, families: bool) -> Option<&str> {
    match kind {
        ParameterKind::Expression { data_type } | ParameterKind::Constant { data_type } => {
            Some(data_type)
        }
        ParameterKind::Collection { data_type, .. } => Some(data_type),
        ParameterKind::Any {
            family: Some(family),
        } if families => Some(family.widest()),
        ParameterKind::Any { .. }
        | ParameterKind::Enum { .. }
        | ParameterKind::Relation { .. }
        | ParameterKind::ColumnOf { .. } => None,
    }
}

/// The name of parameter `index`'s stand-in column.
fn stand_in_column(index: usize) -> String {
    format!("p{index}")
}

/// The query selecting the body with stand-ins for its arguments, and the stand-ins' relation,
/// unless the body reads relations or columns.
fn body_probe(
    definition: &SqlMacroDefinition,
    body: &ExpandedText,
    families: bool,
) -> Option<(String, Value)> {
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
            "type": stand_in_type(&parameter.kind, families).unwrap_or(UNKNOWN_TYPE_HINT),
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
    let Some((probe, table)) = body_probe(definition, body, false) else {
        return Ok(());
    };
    let dialect: &str = adapter_dialect(adapter);
    let key: String = format!("returns\n{dialect}\n{table}\n{probe}");
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

/// The first type error the body's probe shows, as polyglot reports it.
fn body_type_error(probe: &str, table: Value, dialect: &str) -> Option<String> {
    let schema: ValidationSchema = serde_json::from_value(json!({ "tables": [table] })).ok()?;
    let dialect_type: DialectType = dialect.parse().ok()?;
    let options: SchemaValidationOptions = SchemaValidationOptions {
        check_types: true,
        strict: Some(false),
        ..Default::default()
    };
    validate_with_schema(probe, dialect_type, &schema, &options)
        .errors
        .into_iter()
        .find(|error| is_type_code(&error.code))
        .map(|error| error.message)
}

/// Whether a polyglot validation code reports an operand or argument of the wrong type.
fn is_type_code(code: &str) -> bool {
    let Some(number) = code
        .get(1..)
        .and_then(|digits| digits.parse::<usize>().ok())
    else {
        return false;
    };
    (code.starts_with('E') && (TYPE_ERROR_CODES.0..=TYPE_ERROR_CODES.1).contains(&number))
        || (code.starts_with('W')
            && (TYPE_WARNING_CODES.0..=TYPE_WARNING_CODES.1).contains(&number))
}

/// Rejects a body that misuses an `ANY` family argument, typed as the family's widest member.
pub(crate) fn check_body_types(
    definition: &SqlMacroDefinition,
    body: &ExpandedText,
    (adapter, location): (&str, SqlMacroLocation),
) -> Result<(), SqlMacroError> {
    let families: Vec<String> = definition
        .parameters
        .iter()
        .filter_map(|parameter| match parameter.kind {
            ParameterKind::Any {
                family: Some(family),
            } => Some(format!("{} ANY {}", parameter.name, family.keyword())),
            _ => None,
        })
        .collect();
    if families.is_empty() {
        return Ok(());
    }
    let Some((probe, table)) = body_probe(definition, body, true) else {
        return Ok(());
    };
    let dialect: &str = adapter_dialect(adapter);
    let key: String = format!("types\n{dialect}\n{table}\n{probe}");
    let verdicts = VERDICTS.get_or_init(|| Mutex::new(HashMap::new()));
    let known: Option<Option<String>> = verdicts
        .lock()
        .ok()
        .and_then(|verdicts| verdicts.get(&key).cloned());
    let found: Option<String> = match known {
        Some(found) => found,
        None => {
            let found: Option<String> = body_type_error(&probe, table, dialect);
            if let Ok(mut verdicts) = verdicts.lock() {
                verdicts.insert(key, found.clone());
            }
            found
        }
    };
    let Some(found) = found else {
        return Ok(());
    };
    Err(SqlMacroError::new(
        BODY_TYPE_CODE,
        format!(
            "body of macro {}() does not accept every value of {}: {found}",
            definition.name,
            families.join(", ")
        ),
    )
    .at(location)
    .helped("an ANY family argument may be any type of its family; the body is checked with the family's widest type, so CAST the argument or narrow its declared type"))
}
