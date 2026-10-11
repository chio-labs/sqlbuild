//! The recursion of `normalize_sql_value`, with Python's accounting and diagnostics.

use std::cell::Cell;

use crate::sql_values::_helpers::decimals::{decimal_text, parse_decimal};
use crate::sql_values::_helpers::reprs::{identity_repr, payload_repr};
use crate::sql_values::constants::{
    BOOLEAN_SIZE, DECIMAL_KIND, DELIMITER_SIZE, NULL_SIZE, POSITIVE_ZERO, SCALAR_KINDS,
};
use crate::sql_values::errors::SqlValueFailure;
use crate::sql_values::models::{RawKey, RawSqlValue, SqlValueLimits};
use sqlbuild_core::json::main::python_float_repr::python_float_repr;
use sqlbuild_core::models::{SqlLogicalType, SqlValue, SqlValueKind};
use sqlbuild_core::text::main::active_python_text::active_python_text;
use sqlbuild_core::text::main::python_str_repr::python_str_repr;

type Normalized = Result<SqlValue, SqlValueFailure>;

/// The running totals one normalization accounts against its limits.
pub(crate) struct Normalization<'a> {
    pub(crate) context: &'a str,
    pub(crate) limits: SqlValueLimits,
    pub(crate) elements: Cell<i64>,
    pub(crate) size: Cell<i64>,
}

/// One value's place: its diagnostic path and nesting depth.
#[derive(Clone, Copy)]
pub(crate) struct Place<'p> {
    pub(crate) path: &'p str,
    pub(crate) depth: i64,
}

fn invalid(message: String) -> SqlValueFailure {
    SqlValueFailure::Invalid(message)
}

impl Normalization<'_> {
    fn fail(&self, path: &str, problem: &str) -> SqlValueFailure {
        invalid(format!("{}{path} {problem}", self.context))
    }

    fn account(&self, path: &str, (elements, size): (i64, i64)) -> Result<(), SqlValueFailure> {
        self.elements.set(self.elements.get() + elements);
        self.size.set(self.size.get() + size);
        if self.elements.get() > self.limits.max_elements {
            return Err(self.fail(
                path,
                &format!(
                    "exceeds the maximum element count of {}",
                    self.limits.max_elements
                ),
            ));
        }
        if self.size.get() > self.limits.max_size {
            return Err(self.fail(
                path,
                &format!(
                    "exceeds the maximum value size of {} bytes",
                    self.limits.max_size
                ),
            ));
        }
        Ok(())
    }
}

fn text_size(text: &str) -> i64 {
    text.len() as i64 + DELIMITER_SIZE
}

fn type_name(raw: &RawSqlValue) -> &str {
    match raw {
        RawSqlValue::Null => "NoneType",
        RawSqlValue::Bool(_) => "bool",
        RawSqlValue::Int(_) | RawSqlValue::BigInt(_) => "int",
        RawSqlValue::Float(_) => "float",
        RawSqlValue::Decimal(_) => "Decimal",
        RawSqlValue::Str(_) => "str",
        RawSqlValue::List(_) => "list",
        RawSqlValue::Set(_) => "AuthoredSqlSet",
        RawSqlValue::Object(_) => "dict",
        RawSqlValue::Call(_) => "AuthoredSqlValueCall",
        RawSqlValue::Other(name) => name,
    }
}

fn scalar_decimal(state: &Normalization<'_>, path: &str, text: &str) -> Normalized {
    let number = parse_decimal(text).ok_or_else(|| state.fail(path, "has an invalid decimal"))?;
    if number.special.is_some() {
        return Err(state.fail(
            path,
            &format!("decimal must be finite; received Decimal('{text}')"),
        ));
    }
    state.account(path, (0, text.chars().count() as i64))?;
    Ok(SqlValue::Decimal(decimal_text(&number)))
}

fn scalar(raw: &RawSqlValue, state: &Normalization<'_>, path: &str) -> Option<Normalized> {
    Some(match raw {
        RawSqlValue::Null => state.account(path, (0, NULL_SIZE)).map(|()| SqlValue::Null),
        RawSqlValue::Bool(flag) => state
            .account(path, (0, BOOLEAN_SIZE))
            .map(|()| SqlValue::Boolean(*flag)),
        RawSqlValue::Int(number) => state
            .account(path, (0, number.to_string().len() as i64))
            .map(|()| SqlValue::Integer(*number)),
        RawSqlValue::BigInt(digits) => Err(state.fail(
            path,
            &format!("integer {digits} is outside the signed 64-bit range"),
        )),
        RawSqlValue::Float(number) if !number.is_finite() => Err(state.fail(
            path,
            &format!(
                "float must be finite; received {}",
                python_float_repr(*number)
            ),
        )),
        RawSqlValue::Float(number) => {
            let normalized = if *number == POSITIVE_ZERO {
                POSITIVE_ZERO
            } else {
                *number
            };
            state
                .account(path, (0, python_float_repr(normalized).len() as i64))
                .map(|()| SqlValue::Float(normalized))
        }
        RawSqlValue::Decimal(text) => scalar_decimal(state, path, text),
        RawSqlValue::Str(text) => state
            .account(path, (0, text_size(text)))
            .map(|()| SqlValue::String(text.clone())),
        _ => return None,
    })
}

/// `_normalize`: one authored value at `place`, typed by `explicit_type` when given.
pub(crate) fn normalize(
    raw: &RawSqlValue,
    place: Place<'_>,
    state: &Normalization<'_>,
    explicit_type: Option<&str>,
) -> Normalized {
    if place.depth > state.limits.max_depth {
        return Err(state.fail(
            place.path,
            &format!(
                "exceeds the maximum nesting depth of {}",
                state.limits.max_depth
            ),
        ));
    }
    if let Some(explicit) = explicit_type {
        return explicit_scalar(raw, place.path, state, explicit);
    }
    if let Some(normalized) = scalar(raw, state, place.path) {
        return normalized;
    }
    match raw {
        RawSqlValue::List(items) => collection(items, SqlValueKind::List, place, state),
        RawSqlValue::Set(items) => collection(items, SqlValueKind::Set, place, state),
        RawSqlValue::Object(entries) => object(entries, place, state),
        _ => Err(state.fail(
            place.path,
            &format!(
                "has unsupported type {}; expected a scalar, list, set, or object",
                type_name(raw)
            ),
        )),
    }
}

fn explicit_decimal(raw: &RawSqlValue, path: &str, state: &Normalization<'_>) -> Normalized {
    let RawSqlValue::Str(text) = raw else {
        return Err(state.fail(
            path,
            &format!(
                "with type decimal requires a quoted decimal string; received {}",
                type_name(raw)
            ),
        ));
    };
    let quoted = python_str_repr(active_python_text(), text);
    let number = parse_decimal(text)
        .ok_or_else(|| state.fail(path, &format!("has invalid decimal value {quoted}")))?;
    if number.special.is_some() {
        return Err(state.fail(path, &format!("decimal must be finite; received {quoted}")));
    }
    state.account(path, (0, text.chars().count() as i64))?;
    Ok(SqlValue::Decimal(decimal_text(&number)))
}

fn explicit_scalar(
    raw: &RawSqlValue,
    path: &str,
    state: &Normalization<'_>,
    explicit: &str,
) -> Normalized {
    let kind = explicit.to_lowercase();
    let known =
        ["list", "set", "object"].contains(&kind.as_str()) || SCALAR_KINDS.contains(&kind.as_str());
    if !known {
        return Err(state.fail(
            path,
            &format!(
                "has unsupported explicit type '{explicit}'; expected {}",
                SCALAR_KINDS.join(", ")
            ),
        ));
    }
    if !SCALAR_KINDS.contains(&kind.as_str()) {
        return Err(state.fail(
            path,
            &format!("explicit type '{explicit}' is not a scalar type"),
        ));
    }
    if kind == DECIMAL_KIND {
        return explicit_decimal(raw, path, state);
    }
    let matches = matches!(
        (kind.as_str(), raw),
        ("string", RawSqlValue::Str(_))
            | ("integer", RawSqlValue::Int(_) | RawSqlValue::BigInt(_))
            | ("boolean", RawSqlValue::Bool(_))
            | ("float", RawSqlValue::Float(_))
            | ("null", RawSqlValue::Null)
    );
    if !matches {
        return Err(state.fail(
            path,
            &format!("has type {}; expected {kind}", type_name(raw)),
        ));
    }
    normalize(raw, Place { path, depth: 1 }, state, None)
}

fn element_type(
    values: &[SqlValue],
    path: &str,
    kind: SqlValueKind,
    state: &Normalization<'_>,
) -> Result<SqlLogicalType, SqlValueFailure> {
    let expected = values
        .iter()
        .find(|value| !matches!(value, SqlValue::Null))
        .map(SqlValue::logical_type)
        .ok_or_else(|| {
            state.fail(
                path,
                &format!(
                    "{} cannot infer an element type from only null values",
                    kind.as_str()
                ),
            )
        })?;
    for (index, value) in values.iter().enumerate() {
        let logical = value.logical_type();
        if !matches!(value, SqlValue::Null) && logical != expected {
            return Err(state.fail(
                &format!("{path}[{index}]"),
                &format!(
                    "has type {}; expected {}",
                    logical.display_name(),
                    expected.display_name()
                ),
            ));
        }
    }
    Ok(expected)
}

fn canonical_set(
    values: Vec<SqlValue>,
    path: &str,
    state: &Normalization<'_>,
) -> Result<Vec<SqlValue>, SqlValueFailure> {
    let mut keyed: Vec<(String, SqlValue)> = Vec::with_capacity(values.len());
    for (index, value) in values.into_iter().enumerate() {
        let identity = identity_repr(&value)?;
        if keyed.iter().any(|(seen, _)| *seen == identity) {
            return Err(state.fail(
                path,
                &format!(
                    "contains duplicate set value {} at {path}[{index}]",
                    payload_repr(&value)
                ),
            ));
        }
        keyed.push((identity, value));
    }
    keyed.sort_by(|(left, _), (right, _)| left.cmp(right));
    Ok(keyed.into_iter().map(|(_, value)| value).collect())
}

fn collection(
    items: &[RawSqlValue],
    kind: SqlValueKind,
    place: Place<'_>,
    state: &Normalization<'_>,
) -> Normalized {
    let path = place.path;
    if items.is_empty() {
        return Err(state.fail(
            path,
            &format!("{} must contain at least one value", kind.as_str()),
        ));
    }
    let count = items.len() as i64;
    state.account(path, (count, DELIMITER_SIZE + count))?;
    let mut values: Vec<SqlValue> = Vec::with_capacity(items.len());
    for (index, item) in items.iter().enumerate() {
        let item_path = format!("{path}[{index}]");
        let item_place = Place {
            path: &item_path,
            depth: place.depth + 1,
        };
        values.push(normalize(item, item_place, state, None)?);
    }
    let element = element_type(&values, path, kind, state)?;
    if kind == SqlValueKind::Set {
        let values = canonical_set(values, path, state)?;
        return Ok(SqlValue::Set {
            element_type: element,
            values,
        });
    }
    Ok(SqlValue::List {
        element_type: element,
        values,
    })
}

fn object(
    entries: &[(RawKey, RawSqlValue)],
    place: Place<'_>,
    state: &Normalization<'_>,
) -> Normalized {
    let path = place.path;
    let count = entries.len() as i64;
    state.account(path, (count, DELIMITER_SIZE + count))?;
    let mut normalized: Vec<(String, SqlValue)> = Vec::with_capacity(entries.len());
    for (key, item) in entries {
        let key = match key {
            RawKey::Str(key) => key,
            RawKey::Other(repr) => {
                return Err(state.fail(path, &format!("object key {repr} must be a string")));
            }
        };
        state.account(path, (0, text_size(key)))?;
        let item_path = if path.is_empty() {
            format!(".{key}")
        } else {
            format!("{path}.{key}")
        };
        let item_place = Place {
            path: &item_path,
            depth: place.depth + 1,
        };
        normalized.push((key.clone(), normalize(item, item_place, state, None)?));
    }
    normalized.sort_by(|(left, _), (right, _)| left.cmp(right));
    Ok(SqlValue::Object(normalized))
}
