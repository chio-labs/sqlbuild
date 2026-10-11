//! `_parse_constant_declaration` and `typed_constant_declaration`.

use crate::declarations::_helpers::names::declaration_name;
use crate::declarations::constants::{
    COLLECTION_RENDERINGS, RENDER_AS_OPTION, TYPE_OPTION, VALUE_OPTION, WRAPPER_OPTIONS,
};
use crate::declarations::errors::DeclarationFailure;
use crate::declarations::models::{ConstantFacts, DeclarationSite};
use crate::sql_values::errors::SqlValueFailure;
use crate::sql_values::main::normalize_sql_value::normalize_sql_value;
use crate::sql_values::models::{RawSqlValue, SqlValueLimits};
use sqlbuild_core::models::{SqlValue, SqlValueKind};

fn parse(message: String) -> DeclarationFailure {
    DeclarationFailure::Parse(message)
}

/// `_parse_constant_option`: an absent option, or a non-empty string.
fn option(
    raw: Option<&RawSqlValue>,
    file_path: &str,
    label: &str,
) -> Result<Option<String>, DeclarationFailure> {
    match raw {
        None => Ok(None),
        Some(RawSqlValue::Str(text)) if !text.is_empty() => Ok(Some(text.clone())),
        Some(_) => Err(parse(format!("{file_path} {label} must be an identifier"))),
    }
}

/// `typed_constant_declaration`: the typed value of a constant whose name and options are valid.
pub(crate) fn typed_constant(
    name: &str,
    raw: &RawSqlValue,
    options: (Option<&str>, Option<&str>),
    file_path: &str,
) -> Result<ConstantFacts, DeclarationFailure> {
    let (explicit_type, render_as) = options;
    let render_as = match render_as {
        None => None,
        Some(text) => Some(
            COLLECTION_RENDERINGS
                .iter()
                .copied()
                .find(|known| *known == text)
                .ok_or_else(|| {
                    parse(format!(
                        "{file_path} constant '{name}' render_as must be value_list or array"
                    ))
                })?,
        ),
    };
    let context = format!("{file_path} constant '{name}'");
    let value: SqlValue =
        normalize_sql_value(raw, &context, explicit_type, SqlValueLimits::default()).map_err(
            |failure| match failure {
                SqlValueFailure::Invalid(message) => parse(message),
                SqlValueFailure::DecimalOverflow => DeclarationFailure::DecimalOverflow,
            },
        )?;
    let kind = value.logical_type().kind;
    if let Some(rendering) = render_as
        && !matches!(kind, SqlValueKind::List | SqlValueKind::Set)
    {
        return Err(parse(format!(
            "{file_path} constant '{name}' is {} and does not support render_as {rendering}",
            kind.as_str()
        )));
    }
    Ok(ConstantFacts {
        name: name.to_owned(),
        value,
        render_as,
    })
}

fn wrapper_option<'a>(
    arguments: &'a [(String, RawSqlValue)],
    key: &str,
) -> Option<&'a RawSqlValue> {
    arguments
        .iter()
        .rev()
        .find(|(name, _)| name == key)
        .map(|(_, value)| value)
}

/// A model-header constant: a plain value or a `constant(value := ..., type := ..., ...)` call.
pub(crate) fn header_constant(
    raw_name: &RawSqlValue,
    raw_value: &RawSqlValue,
    site: DeclarationSite<'_>,
) -> Result<ConstantFacts, DeclarationFailure> {
    let file_path = site.file_path;
    let name = declaration_name(raw_name, site, "constant")?;
    let RawSqlValue::Call(arguments) = raw_value else {
        return typed_constant(&name, raw_value, (None, None), file_path);
    };
    let mut unknown: Vec<&str> = arguments
        .iter()
        .map(|(key, _)| key.as_str())
        .filter(|key| !WRAPPER_OPTIONS.contains(key))
        .collect();
    unknown.sort_unstable();
    unknown.dedup();
    if !unknown.is_empty() {
        return Err(parse(format!(
            "{file_path} constant '{name}' wrapper has unknown keys: {}",
            unknown.join(", ")
        )));
    }
    let Some(value) = wrapper_option(arguments, VALUE_OPTION) else {
        return Err(parse(format!(
            "{file_path} constant '{name}' is missing required value"
        )));
    };
    let explicit = option(
        wrapper_option(arguments, TYPE_OPTION),
        file_path,
        &format!("constant '{name}' type"),
    )?;
    let render_as = option(
        wrapper_option(arguments, RENDER_AS_OPTION),
        file_path,
        &format!("constant '{name}' render_as"),
    )?;
    typed_constant(
        &name,
        value,
        (explicit.as_deref(), render_as.as_deref()),
        file_path,
    )
}
