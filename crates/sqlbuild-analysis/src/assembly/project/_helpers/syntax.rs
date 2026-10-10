//! Python's syntax validation: Polyglot's `validate` or `parse_one` of the cleaned SQL.

use std::collections::HashMap;

use polyglot_sql::{
    ComplexityGuardOptions, Dialect, DialectType, ParseOptions, ValidationOptions,
    validate_with_dialect,
};

use crate::assembly::project::constants::{
    INVALID_SQL, MAX_FUNCTION_CALL_DEPTH, NORMALIZATION_DEFERRAL, UNSUPPORTED_DIALECT_DEFERRAL,
};
use sqlbuild_sqltext::compiler::main::placeholder_defaults::placeholder_defaults;

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
        .map_err(|unknown| SyntaxFailure::UnknownDialect(unknown.to_owned()))?;
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
