//! Python's `validate_sql_syntax` and `validate_hook_sql_syntax` outcome, without the message.

use std::collections::HashMap;

use polyglot_sql::{
    ComplexityGuardOptions, Dialect, DialectType, ValidationOptions, validate_with_dialect,
};
use serde_json::json;

use crate::assembly::project::constants::{
    DIALECT_DEFERRAL, MAX_FUNCTION_CALL_DEPTH, NORMALIZATION_DEFERRAL, PLACEHOLDER_DEFERRAL,
    PLACEHOLDER_PREFIX, UNSUPPORTED_DIALECT_DEFERRAL,
};
use crate::assembly::project::models::SyntaxCheck;
use crate::assembly::project::types::Fact;
use crate::lineage::main::parser_dialect::parser_dialect;
use crate::semantic_validation::main::normalize::normalize_analysis_sql;
use crate::semantic_validation::models::NormalizationInput;

/// Whether Polyglot's `validate` accepts the cleaned SQL; Python raises where it does not.
pub(crate) fn syntax_valid(check: &SyntaxCheck, dialect: &str) -> Fact<bool> {
    let cleaned: String = normalize_analysis_sql(NormalizationInput {
        sql: check.sql.clone(),
        dialect: dialect.to_owned(),
        stubs: HashMap::new(),
        placeholders: HashMap::new(),
    })
    .map_err(|_| NORMALIZATION_DEFERRAL.to_owned())?;
    let cleaned: String = if check.placeholders.is_empty() {
        cleaned
    } else {
        placeholder_defaults(&cleaned, &check.placeholders)?
    };
    let dialect: DialectType =
        parser_dialect(Some(dialect)).ok_or_else(|| UNSUPPORTED_DIALECT_DEFERRAL.to_owned())?;
    let complexity_guard: ComplexityGuardOptions =
        serde_json::from_value(json!({"maxFunctionCallDepth": MAX_FUNCTION_CALL_DEPTH}))
            .map_err(|_| DIALECT_DEFERRAL.to_owned())?;
    let options = ValidationOptions {
        complexity_guard: Some(complexity_guard),
        strict_syntax: false,
        semantic: false,
    };
    Ok(validate_with_dialect(&cleaned, &Dialect::get(dialect), &options).valid)
}

/// `substitute_placeholder_defaults`: `@@@name` becomes its default; unknown names stay.
fn placeholder_defaults(sql: &str, placeholders: &[(String, String)]) -> Fact<String> {
    let mut result: String = String::with_capacity(sql.len());
    let mut rest: &str = sql;
    while let Some(start) = rest.find(PLACEHOLDER_PREFIX) {
        result.push_str(&rest[..start]);
        let after: &str = &rest[start + PLACEHOLDER_PREFIX.len()..];
        let length: usize = after
            .find(|character: char| !is_word(character))
            .unwrap_or(after.len());
        if after[length..]
            .chars()
            .next()
            .is_some_and(|next| !next.is_ascii())
        {
            return Err(PLACEHOLDER_DEFERRAL.to_owned());
        }
        if length == 0 {
            result.push_str(&rest[start..=start]);
            rest = &rest[start + 1..];
            continue;
        }
        let name: &str = &after[..length];
        match placeholders
            .iter()
            .find(|(placeholder, _)| placeholder == name)
        {
            Some((_, default)) => result.push_str(default),
            None => {
                result.push_str(PLACEHOLDER_PREFIX);
                result.push_str(name);
            }
        }
        rest = &after[length..];
    }
    result.push_str(rest);
    Ok(result)
}

/// An ASCII character Python's `\w` matches.
fn is_word(character: char) -> bool {
    character.is_ascii_alphanumeric() || character == '_'
}
