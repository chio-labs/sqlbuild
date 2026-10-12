//! `build_scenario_inputs`: SQL scenarios expanded, classified and checked natively.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use sqlbuild_analysis::compiler::main::sql_scenario_classification::extract_scenario;
use sqlbuild_analysis::compiler::models::{SqlScenarioCtes, SqlTestCteText};
use sqlbuild_attachments::test_targets::main::scenario_source_violation::scenario_source_violation;
use sqlbuild_attachments::test_targets::models::ScenarioCteSources;
use sqlbuild_sqltext::sql_references::models::SqlReference;

use crate::bindings::_helpers::compiled_project::model_loop::compile_error;
use crate::bindings::_helpers::compiled_project::model_loop_calls::origin_references;
use crate::bindings::_helpers::compiled_project::source_loop::{
    AuthoredExpansion, expanded_authored_sql, scoped_declarations,
};
use crate::bindings::_helpers::compiled_project::sql_test_loop::{
    FileOrigin, TestScope, assertion_targets, checked_body, source_names, unique,
};

/// A scenario file's paths, discovered file, contents, SQL body and name.
pub(crate) type ScenarioRow = (String, String, Py<PyAny>, String, String, String);

impl<'py> TestScope<'_, 'py> {
    /// Every scenario expanded, classified and checked, in discovery order.
    pub(crate) fn attached_scenarios(&self, rows: &[ScenarioRow]) -> PyResult<Vec<Py<PyAny>>> {
        rows.iter().map(|row| self.scenario(row)).collect()
    }

    fn scenario(&self, row: &ScenarioRow) -> PyResult<Py<PyAny>> {
        let py: Python<'py> = self.context.host.py();
        let (file_path, relative_path, scenario_file, contents, sql_body, name) = row;
        let resource: Bound<'py, PyAny> = self
            .context
            .classes
            .visibility
            .resource_identity
            .call1((self.settings.scenario_kind.bind(py), name))?;
        let declarations: Bound<'py, PyAny> =
            scoped_declarations(self.context, file_path, &resource)?;
        let expansion: AuthoredExpansion<'py> =
            expanded_authored_sql(self.context, (sql_body, file_path), &declarations)?;
        let stem: &str = std::path::Path::new(file_path)
            .file_stem()
            .and_then(|stem| stem.to_str())
            .unwrap_or_default();
        let sql: String = checked_body(
            self.model_loop,
            self.context,
            &expansion.sql,
            &format!("SQL scenario '{stem}'"),
        )?;
        let ctes: SqlScenarioCtes = extract_scenario(&sql, relative_path, &self.model_loop.syntax)
            .map_err(|message| compile_error(self.context.classes, &message, None))?;
        let origin: FileOrigin<'_> = (file_path, relative_path, contents);
        self.checked_scenario_sources(&ctes, origin)?;
        let assertions: Vec<SqlTestCteText> = texts(&ctes.assertions);
        let targets: Vec<String> =
            assertion_targets(self.context, self.model_loop, &assertions, origin)?;
        let fields: Bound<'py, PyDict> = PyDict::new(py);
        fields.set_item("scenario_file", scenario_file.bind(py))?;
        fields.set_item("sql_body", &sql)?;
        fields.set_item("authored_ctes", self.scenario_ctes(&ctes.authored)?)?;
        fields.set_item("expected_ctes", self.scenario_ctes(&ctes.expected)?)?;
        fields.set_item("assertion_ctes", self.scenario_ctes(&ctes.assertions)?)?;
        fields.set_item(
            "source_fixture_names",
            PyTuple::new(py, &ctes.source_fixtures)?,
        )?;
        fields.set_item("ref_fixture_names", PyTuple::new(py, &ctes.ref_fixtures)?)?;
        fields.set_item("seed_fixture_names", PyTuple::new(py, &ctes.seed_fixtures)?)?;
        fields.set_item(
            "dbt_ref_fixture_names",
            PyTuple::new(py, &ctes.dbt_ref_fixtures)?,
        )?;
        fields.set_item(
            "expected_model_names",
            PyTuple::new(py, &ctes.expected_models)?,
        )?;
        fields.set_item("assertion_names", PyTuple::new(py, &ctes.assertion_names)?)?;
        fields.set_item("assertion_target_model_names", PyTuple::new(py, &targets)?)?;
        fields.set_item(
            "target_model_names",
            PyTuple::new(
                py,
                unique(ctes.expected_models.iter().cloned().chain(targets)),
            )?,
        )?;
        fields.set_item("declaration_usages", &expansion.usages)?;
        Ok(self
            .settings
            .scenario_input
            .bind(py)
            .call((), Some(&fields))?
            .unbind())
    }

    /// `_validate_scenario_source_references`: disallowed source reads, then a scan's error.
    fn checked_scenario_sources(
        &self,
        ctes: &SqlScenarioCtes,
        origin: FileOrigin<'_>,
    ) -> PyResult<()> {
        let checks: usize = ctes.expected.len() + ctes.assertions.len();
        let mut sources: Vec<ScenarioCteSources> = Vec::new();
        let mut failure: Option<PyErr> = None;
        let all = ctes
            .expected
            .iter()
            .chain(&ctes.assertions)
            .chain(&ctes.authored);
        for (position, (name, body)) in all.enumerate() {
            let references: Vec<SqlReference> =
                match origin_references(self.context, &self.model_loop.syntax, body, origin) {
                    Ok(references) => references,
                    Err(error) => {
                        failure = Some(error);
                        break;
                    }
                };
            sources.push(ScenarioCteSources {
                name: name.clone(),
                check: position < checks,
                sources: source_names(&references),
            });
        }
        if let Some(message) = scenario_source_violation(origin.1, &sources, &self.catalog.sources)
        {
            return Err(compile_error(self.context.classes, &message, None));
        }
        failure.map_or(Ok(()), Err)
    }

    fn scenario_ctes(&self, ctes: &[(String, String)]) -> PyResult<Bound<'py, PyTuple>> {
        let py: Python<'py> = self.context.host.py();
        let mut records: Vec<Bound<'py, PyAny>> = Vec::with_capacity(ctes.len());
        for (name, body) in ctes {
            let fields: Bound<'py, PyDict> = PyDict::new(py);
            fields.set_item("name", name)?;
            fields.set_item("sql_body", body)?;
            records.push(
                self.settings
                    .scenario_cte
                    .bind(py)
                    .call((), Some(&fields))?,
            );
        }
        PyTuple::new(py, records)
    }
}

fn texts(ctes: &[(String, String)]) -> Vec<SqlTestCteText> {
    ctes.iter()
        .map(|(name, body)| SqlTestCteText(name.clone(), body.clone()))
        .collect()
}
