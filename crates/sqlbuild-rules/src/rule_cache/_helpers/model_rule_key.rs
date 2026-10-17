//! `model_rule_key`: the cache key of one model's SQL rule findings.

use crate::rule_cache::_helpers::digest::field_digest;
use crate::rule_cache::constants::{MODEL_KEY_KIND, NO_CONTRACT};
use crate::rule_cache::models::ModelKeyInput;

/// A digest of the lint key, selected codes, authored and compiled SQL and dynamic contract.
#[must_use]
pub(crate) fn model_rule_key(
    lint_key: &str,
    codes: &[String],
    model: &ModelKeyInput<'_>,
) -> String {
    let codes: String = codes.join("\0");
    let contract: &str = model.contract.unwrap_or(NO_CONTRACT);
    let has_contract: &str = if model.contract.is_some() { "1" } else { "0" };
    field_digest(
        MODEL_KEY_KIND,
        &[
            lint_key,
            &codes,
            model.authored_sql,
            model.query_sql,
            has_contract,
            contract,
        ],
    )
}
