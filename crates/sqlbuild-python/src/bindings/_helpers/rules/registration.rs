//! Register the native rules, lint and DSL header functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::rules::{
    builtin_catalogue, custom_rule_cache, custom_rule_evidence, dsl_headers, evaluation, lint,
    lint_expansion, lint_sql_bodies, lint_text, results, rule_cache, rules_config, run_lint,
    selection, skills,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    evaluation::register(module)?;
    lint::register(module)?;
    lint_text::register(module)?;
    lint_expansion::register(module)?;
    lint_sql_bodies::register(module)?;
    dsl_headers::register(module)?;
    custom_rule_evidence::register(module)?;
    rule_cache::register(module)?;
    custom_rule_cache::register(module)?;
    builtin_catalogue::register(module)?;
    rules_config::register(module)?;
    run_lint::register(module)?;
    selection::register(module)?;
    results::register(module)?;
    skills::register(module)
}
