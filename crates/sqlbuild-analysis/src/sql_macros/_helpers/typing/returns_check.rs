//! An expression macro's body typed from its declared arguments and checked against `returns`.

use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

use polyglot_sql::expressions::DataType;
use polyglot_sql::{DialectType, SchemaValidationOptions, ValidationSchema, validate_with_schema};
use serde_json::{Value, json};

use crate::query_analysis::main::annotated_output_types::annotated_output_types;
use crate::sql_macros::_helpers::parsing::body::expand_body;
use crate::sql_macros::_helpers::rendering::arguments::type_family;
use crate::sql_macros::_helpers::typing::typed_calls::{
    markable_calls, shifted, typed_sql, without_marker_calls,
};
use crate::sql_macros::constants::{
    BODY_TYPE_CODE, INFERRED_TEXT_TYPE, RETURNS_MISMATCH_CODE, STAND_IN_RELATION, TYPE_ERROR_CODES,
    TYPE_WARNING_CODES, UNKNOWN_TYPE_HINT, VARCHAR_TYPE,
};
use crate::sql_macros::errors::SqlMacroError;
use crate::sql_macros::models::{
    ArgumentShape, BodyType, ExpandedText, ParameterKind, RenderedArgument, SqlMacroDefinition,
    SqlMacroForm, SqlMacroLocation, TypeFamily, TypedCall,
};
use crate::type_system::main::normalize_type::normalize_type;
use crate::type_system::models::TypeNormalization;

/// Each body's type, by the probe that typed it, so a macro is typed once per process.
static BODY_TYPES: OnceLock<Mutex<HashMap<String, BodyType>>> = OnceLock::new();
/// Each body's first type error, by the probe that found it.
static TYPE_ERRORS: OnceLock<Mutex<HashMap<String, Option<String>>>> = OnceLock::new();

/// The dialect an adapter's SQL is analysed in.
pub(crate) fn adapter_dialect(adapter: &str) -> &str {
    match adapter {
        "motherduck" => "duckdb",
        "" => "generic",
        other => other,
    }
}

/// A parameter's stand-in column type, with `ANY` families widened only when `families` is set.
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

/// The body selected over stand-in arguments, and their relation, unless it reads relations.
fn body_probe(
    definition: &SqlMacroDefinition,
    body: &ExpandedText,
    (families, dialect): (bool, &str),
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
    let expansion = match expand_body(definition, body, &arguments) {
        Ok(expansion) => expansion,
        Err(_) => return None,
    };
    let prefix: &str = "SELECT (";
    let unmarked: String = format!("{prefix}{}) AS b FROM {STAND_IN_RELATION}", expansion.sql);
    let calls: Vec<TypedCall> = shifted(expansion.calls, prefix.len()).collect();
    let (probe, _) = typed_sql(&unmarked, &markable_calls(&unmarked, &calls, dialect));
    let table: Value = json!({"name": STAND_IN_RELATION, "columns": columns});
    Some((probe, table))
}

/// What inference knows of the body's type.
fn inferred_body_type(probe: &str, table: Value, dialect: &str) -> BodyType {
    let Ok(schema) = serde_json::from_value::<ValidationSchema>(json!({ "tables": [table] }))
    else {
        return BodyType::Unknown;
    };
    let Some(outputs) = annotated_output_types(probe, dialect, &schema) else {
        return BodyType::Unknown;
    };
    let Some((_, shown, annotated)) = outputs.into_iter().next() else {
        return BodyType::Unknown;
    };
    match (shown, annotated) {
        (Some(shown), _) if !shown.to_ascii_uppercase().contains(UNKNOWN_TYPE_HINT) => {
            BodyType::Known(shown)
        }
        (Some(shown), Some(data_type))
            if data_type.contains_unknown() && data_type != DataType::Unknown =>
        {
            BodyType::PartlyKnown { shown, data_type }
        }
        _ => BodyType::Unknown,
    }
}

/// Whether `returns` cannot fill the unknown components of `partial` without changing its shape.
fn changes_shape(returns: &str, partial: &DataType, dialect: &str) -> bool {
    let Ok(dialect_type) = dialect.parse::<DialectType>() else {
        return false;
    };
    match polyglot_sql::parse_data_type(returns, dialect_type) {
        Ok(declared) => !partial.is_refined_by(&declared),
        Err(_) => false,
    }
}

/// Whether body type `inferred` is outside the family of `returns`, or another non-family type.
fn disagrees(returns: &str, inferred: &str, adapter: &str) -> bool {
    let (declared, found) = (
        type_family(returns, adapter),
        type_family(inferred, adapter),
    );
    if declared != TypeFamily::Unknown && found != TypeFamily::Unknown {
        return declared != found;
    }
    let dialect: &str = adapter_dialect(adapter);
    match (
        normalize_type(returns, dialect),
        normalize_type(inferred, dialect),
    ) {
        (
            Ok(TypeNormalization {
                normalized: declared,
                ..
            }),
            Ok(TypeNormalization {
                normalized: found, ..
            }),
        ) => declared != found,
        _ => false,
    }
}

/// The verdict `cache` holds under `key`, or `compute`'s verdict, cached for the process.
fn remembered<T: Clone>(
    cache: &OnceLock<Mutex<HashMap<String, T>>>,
    key: String,
    compute: impl FnOnce() -> T,
) -> T {
    let verdicts = cache.get_or_init(|| Mutex::new(HashMap::new()));
    let mut verdicts = match verdicts.lock() {
        Ok(verdicts) => verdicts,
        Err(poisoned) => poisoned.into_inner(),
    };
    if let Some(known) = verdicts.get(&key) {
        return known.clone();
    }
    let verdict: T = compute();
    verdicts.insert(key, verdict.clone());
    verdict
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
    let Some((probe, table)) = body_probe(definition, body, (false, adapter_dialect(adapter)))
    else {
        return Ok(());
    };
    let dialect: &str = adapter_dialect(adapter);
    let key: String = format!("returns\n{dialect}\n{table}\n{probe}");
    let body_type: BodyType = remembered(&BODY_TYPES, key, || {
        inferred_body_type(&probe, table, dialect)
    });
    let partial: bool = matches!(body_type, BodyType::PartlyKnown { .. });
    let (shown, wrong): (String, bool) = match body_type {
        BodyType::Unknown => return Ok(()),
        BodyType::Known(inferred) if inferred.eq_ignore_ascii_case(INFERRED_TEXT_TYPE) => (
            VARCHAR_TYPE.to_owned(),
            disagrees(returns, VARCHAR_TYPE, adapter),
        ),
        BodyType::Known(inferred) => {
            let wrong: bool = disagrees(returns, &inferred, adapter);
            (inferred, wrong)
        }
        BodyType::PartlyKnown { shown, data_type } => {
            let wrong: bool = changes_shape(returns, &data_type, dialect);
            (shown, wrong)
        }
    };
    if !wrong {
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
    .helped(if partial {
        format!(
            "declare a returns of the body's shape {shown} with its unknown parts filled in, CAST the body to {returns}, or remove returns to use the inferred type"
        )
    } else {
        format!(
            "declare returns {shown}, CAST the body to {returns}, or remove returns to use the inferred type"
        )
    }))
}

/// The first type error the body's probe shows, as polyglot reports it.
fn body_type_error(probe: &str, table: Value, dialect: &str) -> Option<String> {
    let Ok(schema) = serde_json::from_value::<ValidationSchema>(json!({ "tables": [table] }))
    else {
        return None;
    };
    let dialect_type: DialectType = match dialect.parse() {
        Ok(dialect_type) => dialect_type,
        Err(_) => return None,
    };
    let options: SchemaValidationOptions = SchemaValidationOptions {
        check_types: true,
        strict: Some(false),
        ..Default::default()
    };
    validate_with_schema(probe, dialect_type, &schema, &options)
        .errors
        .into_iter()
        .find(|error| is_type_code(&error.code))
        .map(|error| without_marker_calls(&error.message).into_owned())
}

/// Whether a polyglot validation code reports an operand or argument of the wrong type.
fn is_type_code(code: &str) -> bool {
    let number: usize = match code.get(1..).map(str::parse::<usize>) {
        Some(Ok(number)) => number,
        _ => return false,
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
    let Some((probe, table)) = body_probe(definition, body, (true, adapter_dialect(adapter)))
    else {
        return Ok(());
    };
    let dialect: &str = adapter_dialect(adapter);
    let key: String = format!("types\n{dialect}\n{table}\n{probe}");
    let found: Option<String> = remembered(&TYPE_ERRORS, key, || {
        body_type_error(&probe, table, dialect)
    });
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
