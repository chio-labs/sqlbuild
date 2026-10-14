//! Inference and schema preparation at the fixture Python boundary.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use sqlbuild_analysis::planner_fixtures::main::empty_fixture_marker::empty_fixture_marker;

use crate::bindings::_helpers::boundary::panics::value_error;
use crate::bindings::_helpers::planner_strategy::fixture_sql::complete_empty_fixture_sql;
use crate::bindings::_helpers::planner_strategy::fixture_values::{diagnostic, label};

pub(crate) struct PreparedFixtures<'py> {
    pub(crate) sql: Bound<'py, PyDict>,
    pub(crate) inferred: Bound<'py, PyDict>,
    pub(crate) null_names: Bound<'py, PyDict>,
    pub(crate) quoted_names: Bound<'py, PyDict>,
    pub(crate) diagnostics: Vec<Bound<'py, PyAny>>,
}

pub(crate) fn prepare<'py>(
    groups: &Bound<'py, PyAny>,
    relations: &Bound<'py, PyDict>,
    adapter: &Bound<'py, PyAny>,
    inferences: &Bound<'py, PyAny>,
) -> PyResult<PreparedFixtures<'py>> {
    let py = groups.py();
    let mut prepared = PreparedFixtures {
        sql: PyDict::new(py),
        inferred: PyDict::new(py),
        null_names: PyDict::new(py),
        quoted_names: PyDict::new(py),
        diagnostics: Vec::new(),
    };
    for group in groups.try_iter()? {
        let group = group?;
        let kind = group.get_item(0)?;
        let fixtures = group.get_item(1)?.cast_into::<PyDict>()?;
        for (name, sql) in fixtures.iter() {
            let key = PyTuple::new(py, [&kind, &name])?.into_any();
            let mut sql: String = sql.extract()?;
            if empty_fixture_marker(&sql).map_err(value_error)? {
                let relation = relations
                    .get_item(&key)?
                    .unwrap_or_else(|| py.None().into_bound(py));
                let (empty_sql, error) = complete_empty_fixture_sql(&sql, &relation, adapter)?;
                if let Some(error) = error {
                    prepared
                        .diagnostics
                        .push(diagnostic(&key, &format!("{} {error}", label(&key)?))?);
                    prepared.sql.set_item(&key, &sql)?;
                    continue;
                }
                sql = empty_sql;
            }
            prepared.sql.set_item(&key, &sql)?;
            let kwargs = PyDict::new(py);
            kwargs.set_item("query_sql", &sql)?;
            kwargs.set_item(
                "inference_profile",
                adapter.call_method0("expression_inference_profile")?,
            )?;
            let inference = inferences.call_method("infer", (), Some(&kwargs))?;
            if !inference.is_none() {
                prepared
                    .inferred
                    .set_item(&key, inference.getattr("columns")?)?;
                prepared
                    .null_names
                    .set_item(&key, inference.getattr("null_literal_names")?)?;
                prepared
                    .quoted_names
                    .set_item(&key, inference.getattr("quoted_names")?)?;
            }
        }
    }
    Ok(prepared)
}
