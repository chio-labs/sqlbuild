//! `model_rule_keys`: the SQL rule cache keys of many models, hashed in parallel.

use rayon::iter::{IntoParallelRefIterator, ParallelIterator};

use crate::rule_cache::_helpers::model_rule_key::model_rule_key;
use crate::rule_cache::models::ModelKeyInput;

/// Each model's `model_rule_key`, in input order.
#[must_use]
pub fn model_rule_keys(
    lint_key: &str,
    codes: &[String],
    models: &[ModelKeyInput<'_>],
) -> Vec<String> {
    models
        .par_iter()
        .map(|model| model_rule_key(lint_key, codes, model))
        .collect()
}
