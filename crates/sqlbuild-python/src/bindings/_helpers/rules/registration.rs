//! Register the native rules, lint and DSL header functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::rules::{
    builtin_catalogue, catalogue, custom_rule_cache, custom_rule_evidence, dsl_headers,
    early_sql_lint, evaluation, guidance, lint, lint_expansion, lint_sql_bodies, lint_text,
    results, rule_cache, rule_plan, rule_run, rules_config, run_lint, selection, sql_rules,
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
    rule_run::register(module)?;
    rule_plan::register(module)?;
    sql_rules::register(module)?;
    early_sql_lint::register(module)?;
    custom_rule_cache::register(module)?;
    builtin_catalogue::register(module)?;
    catalogue::register(module)?;
    rules_config::register(module)?;
    run_lint::register(module)?;
    selection::register(module)?;
    results::register(module)?;
    guidance::register(module)
}
