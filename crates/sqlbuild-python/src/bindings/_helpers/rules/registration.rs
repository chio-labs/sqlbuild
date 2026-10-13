//! Register the native rules, lint and DSL header functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::rules::{
    builtin_catalogue, custom_rule_cache, custom_rule_evidence, dsl_headers, evaluation, lint,
    results, rule_cache, rules_config, skills,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    evaluation::register(module)?;
    lint::register(module)?;
    dsl_headers::register(module)?;
    custom_rule_evidence::register(module)?;
    rule_cache::register(module)?;
    custom_rule_cache::register(module)?;
    builtin_catalogue::register(module)?;
    rules_config::register(module)?;
    results::register(module)?;
    skills::register(module)
}
