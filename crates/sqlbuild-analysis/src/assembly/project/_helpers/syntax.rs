//! Python's syntax validation: Polyglot's `validate` or `parse_one` of the cleaned SQL.

use std::collections::HashMap;

use polyglot_sql::{
    ComplexityGuardOptions, Dialect, DialectType, ParseOptions, ValidationOptions,
    validate_with_dialect,
};
use sqlbuild_core::text::main::active_python_text::active_python_text;
use sqlbuild_core::text::main::is_python_word::is_python_word;

use crate::assembly::project::constants::{
    INVALID_SQL, MAX_FUNCTION_CALL_DEPTH, NORMALIZATION_DEFERRAL, PLACEHOLDER_PREFIX,
    UNSUPPORTED_DIALECT_DEFERRAL,
};
use crate::assembly::project::models::{SyntaxCheck, SyntaxFailure, SyntaxMode};
use crate::assembly::project::types::Fact;
use crate::lineage::main::parser_dialect::parser_dialect;
use crate::semantic_validation::main::normalize::normalize_analysis_sql;
use crate::semantic_validation::models::NormalizationInput;

/// Whether Polyglot's `validate` accepts the cleaned SQL; Python raises where it does not.
pub(crate) fn syntax_valid(check: &SyntaxCheck, dialect: &str) -> Fact<bool> {
    match syntax_error(check, dialect, SyntaxMode::Validate) {
        Ok(error) => Ok(error.is_none()),
        Err(SyntaxFailure::Normalization(_)) => Err(NORMALIZATION_DEFERRAL.to_owned()),
        Err(SyntaxFailure::UnknownDialect(_)) => Err(UNSUPPORTED_DIALECT_DEFERRAL.to_owned()),
    }
}

/// Python's syntax error message for one SQL string, None where Polyglot accepts it.
///
/// # Errors
///
/// Where Python raises instead: SQL the analysis normalization rejects, or an unknown dialect.
pub(crate) fn syntax_error(
    check: &SyntaxCheck,
    dialect: &str,
    mode: SyntaxMode,
) -> Result<Option<String>, SyntaxFailure> {
    let cleaned: String = normalize_analysis_sql(NormalizationInput {
        sql: check.sql.clone(),
        dialect: dialect.to_owned(),
        stubs: HashMap::new(),
        placeholders: HashMap::new(),
    })
    .map_err(SyntaxFailure::Normalization)?;
    let cleaned: String = if check.placeholders.is_empty() {
        cleaned
    } else {
        placeholder_defaults(&cleaned, &check.placeholders)
    };
    let dialect_type: DialectType = parser_dialect(Some(dialect))
        .ok_or_else(|| SyntaxFailure::UnknownDialect(dialect.to_owned()))?;
    let complexity_guard = ComplexityGuardOptions {
        max_function_call_depth: Some(MAX_FUNCTION_CALL_DEPTH),
        ..Default::default()
    };
    let polyglot: Dialect = Dialect::get(dialect_type);
    Ok(match mode {
        SyntaxMode::Validate => {
            let options = ValidationOptions {
                complexity_guard: Some(complexity_guard),
                strict_syntax: false,
                semantic: false,
            };
            let result = validate_with_dialect(&cleaned, &polyglot, &options);
            (!result.valid).then(|| {
                result
                    .errors
                    .first()
                    .map_or_else(|| INVALID_SQL.to_owned(), |error| error.message.clone())
            })
        }
        SyntaxMode::Parse => {
            let options = ParseOptions {
                complexity_guard: Some(complexity_guard),
            };
            match polyglot.parse_with_options(&cleaned, &options) {
                Ok(statements) if statements.len() == 1 => None,
                Ok(statements) => Some(format!("Expected 1 statement, found {}", statements.len())),
                Err(error) => Some(error.to_string()),
            }
        }
    })
}

/// `substitute_placeholder_defaults`: `@@@name` becomes its default; unknown names stay.
pub(crate) fn placeholder_defaults(sql: &str, placeholders: &[(String, String)]) -> String {
    let mut result: String = String::with_capacity(sql.len());
    let mut rest: &str = sql;
    while let Some(start) = rest.find(PLACEHOLDER_PREFIX) {
        result.push_str(&rest[..start]);
        let after: &str = &rest[start + PLACEHOLDER_PREFIX.len()..];
        let length: usize = after
            .find(|character: char| !is_word(character))
            .unwrap_or(after.len());
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
    result
}

/// A character Python's `\w` matches.
fn is_word(character: char) -> bool {
    is_python_word(active_python_text(), character)
}
