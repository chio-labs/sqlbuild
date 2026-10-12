//! A finished model outcome's cleaned analysis SQL, normalized on first read for cache hits.

use std::borrow::Cow;
use std::collections::HashMap;

use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::assembly::analysis_session::models::{DeferredCleaning, ModelOutcome};
use crate::semantic_validation::main::normalize::normalize_analysis_sql;
use crate::semantic_validation::models::NormalizationInput;

/// The outcome's cleaned SQL, normalizing a cache hit's deferred input when it has one.
pub fn resolved_cleaned_sql(outcome: &ModelOutcome) -> Result<Cow<'_, str>, String> {
    let Some(DeferredCleaning {
        dialect,
        query_sql,
        placeholders,
    }) = outcome.deferred_cleaning.as_ref()
    else {
        return Ok(Cow::Borrowed(&outcome.cleaned_sql));
    };
    let request: NormalizationInput = NormalizationInput {
        sql: query_sql.clone(),
        dialect: dialect.clone(),
        stubs: HashMap::new(),
        placeholders: placeholders.iter().cloned().collect(),
    };
    catch_compiler_panic(|| normalize_analysis_sql(request)).map(Cow::Owned)
}
