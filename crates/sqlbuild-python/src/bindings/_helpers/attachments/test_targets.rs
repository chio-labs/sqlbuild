//! SQL test target and scenario source validation for the preview compile attachments.

use std::collections::HashSet;

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyclass, pymethods};
use sqlbuild_attachments::test_targets::main::scenario_source_violation::scenario_source_violation;
use sqlbuild_attachments::test_targets::main::unknown_test_target::unknown_test_target;
use sqlbuild_attachments::test_targets::models::{ScenarioCteSources, TargetCatalog, TestTargets};

use crate::bindings::_helpers::boundary::panics::compiler_guard;

/// A model test's target name groups, in `TestTargets` field order.
type TargetRow = (
    Vec<String>,
    Vec<String>,
    Vec<String>,
    Vec<String>,
    Vec<String>,
    Vec<String>,
    Vec<String>,
);

/// The project's resource names, read once per compile and shared by every test and scenario.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct SqlTestTargetCatalog {
    catalog: TargetCatalog,
}

#[pymethods]
impl SqlTestTargetCatalog {
    #[new]
    fn new(
        models: HashSet<String>,
        sources: HashSet<String>,
        seeds: HashSet<String>,
        resources: (HashSet<String>, HashSet<String>),
    ) -> Self {
        let (table_functions, macros) = resources;
        Self {
            catalog: TargetCatalog {
                models,
                sources,
                seeds,
                table_functions,
                macros,
            },
        }
    }

    /// Python's error for a model test's first unknown target, or `None`.
    fn unknown_test_target(
        &self,
        file_label: &str,
        targets: TargetRow,
    ) -> PyResult<Option<String>> {
        compiler_guard(|| {
            let (
                mock_models,
                mock_sources,
                mock_seeds,
                mock_table_functions,
                macro_mocks,
                expected_models,
                assertion_targets,
            ) = targets;
            Ok(unknown_test_target(
                file_label,
                &self.catalog,
                &TestTargets {
                    mock_models,
                    mock_sources,
                    mock_seeds,
                    mock_table_functions,
                    macro_mocks,
                    expected_models,
                    assertion_targets,
                },
            ))
        })
    }

    /// Python's error for a scenario's first disallowed `(cte, is check, sources)` read, or `None`.
    fn scenario_source_error(
        &self,
        file_label: &str,
        ctes: Vec<(String, bool, Vec<String>)>,
    ) -> PyResult<Option<String>> {
        compiler_guard(|| {
            let mut cte_sources: Vec<ScenarioCteSources> = Vec::with_capacity(ctes.len());
            for (name, check, sources) in ctes {
                cte_sources.push(ScenarioCteSources {
                    name,
                    check,
                    sources,
                });
            }
            Ok(scenario_source_violation(
                file_label,
                &cte_sources,
                &self.catalog.sources,
            ))
        })
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<SqlTestTargetCatalog>()?;
    Ok(())
}
