//! SQL test target and scenario source validation for the preview compile attachments.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_attachments::test_targets::main::scenario_source_violation::scenario_source_violation;
use sqlbuild_attachments::test_targets::main::unknown_test_target::unknown_test_target;
use sqlbuild_attachments::test_targets::models::{ScenarioCteSources, TargetGroup};

use crate::bindings::_helpers::boundary::panics::compiler_guard;

/// Python's error for the first unknown `(phrase, names, known names)` target, or `None`.
#[pyfunction]
fn unknown_sql_test_target(
    file_label: &str,
    groups: Vec<(String, Vec<String>, Vec<String>)>,
) -> PyResult<Option<String>> {
    compiler_guard(|| {
        let mut target_groups: Vec<TargetGroup> = Vec::with_capacity(groups.len());
        for (phrase, names, known) in groups {
            target_groups.push(TargetGroup {
                phrase,
                names,
                known,
            });
        }
        Ok(unknown_test_target(file_label, &target_groups))
    })
}

/// Python's error for the first disallowed `(cte, is check, sources)` source read, or `None`.
#[pyfunction]
fn scenario_source_error(
    file_label: &str,
    ctes: Vec<(String, bool, Vec<String>)>,
    known_sources: Vec<String>,
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
            &known_sources,
        ))
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(unknown_sql_test_target, module)?)?;
    module.add_function(wrap_pyfunction!(scenario_source_error, module)?)?;
    Ok(())
}
