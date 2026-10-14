//! Convert project views into pure scenario dependency facts.

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::graph::keys::{KeyCache, native_key};
use crate::bindings::_helpers::planner_scenario::values::{CONSTANTS, MODELS, TYPES, string};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, pyfunction};
use pyo3::types::PyTuple;
use sqlbuild_analysis::planner_scenario::main::graph::graph;
use sqlbuild_analysis::planner_scenario::models::ScenarioGraphInput;

#[pyfunction]
#[pyo3(signature = (*, scenario, project, sql_analysis_enabled=true, sql_analysis_dialect=None))]
pub(crate) fn plan_scenario_graph<'py>(
    scenario: &Bound<'py, PyAny>,
    project: &Bound<'py, PyAny>,
    sql_analysis_enabled: bool,
    sql_analysis_dialect: Option<&str>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyTuple>)> {
    let _ = (sql_analysis_enabled, sql_analysis_dialect);
    let py = scenario.py();
    let mut input = ScenarioGraphInput {
        name: scenario.getattr("name")?.extract()?,
        expected: scenario.getattr("expected_model_names")?.extract()?,
        assertions: scenario
            .getattr("assertion_target_model_names")?
            .extract()?,
        targets: scenario.getattr("target_model_names")?.extract()?,
        refs: scenario.getattr("ref_fixture_names")?.extract()?,
        sources: scenario.getattr("source_fixture_names")?.extract()?,
        seeds: scenario.getattr("seed_fixture_names")?.extract()?,
        dbt_refs: scenario.getattr("dbt_ref_fixture_names")?.extract()?,
        ..ScenarioGraphInput::default()
    };
    for model in project.getattr("models")?.try_iter()? {
        let model = model?;
        let deps = model
            .getattr("deps")?
            .try_iter()?
            .map(|dep| native_key(&dep?))
            .collect::<PyResult<_>>()?;
        input.models.insert(model.getattr("name")?.extract()?, deps);
    }
    for source in project.getattr("sources")?.try_iter()? {
        input
            .project_sources
            .insert(source?.getattr("name")?.extract()?);
    }
    for seed in project.getattr("seeds")?.try_iter()? {
        input
            .project_seeds
            .insert(seed?.getattr("name")?.extract()?);
    }
    let output = graph(&input);
    input.targets.sort();
    input.assertions.sort();
    let plan = call_with(
        &imported(py, MODELS, "ScenarioGraphPlan")?,
        &[
            ("key", scenario.getattr("key")?),
            ("name", scenario.getattr("name")?),
            (
                "target_model_names",
                PyTuple::new(py, input.targets)?.into_any(),
            ),
            (
                "assertion_target_model_names",
                PyTuple::new(py, input.assertions)?.into_any(),
            ),
            ("model_names", PyTuple::new(py, output.models)?.into_any()),
            (
                "source_fixture_names",
                PyTuple::new(py, output.sources)?.into_any(),
            ),
            (
                "ref_fixture_names",
                PyTuple::new(py, output.refs)?.into_any(),
            ),
            ("seed_names", PyTuple::new(py, output.seeds)?.into_any()),
            (
                "seed_fixture_names",
                PyTuple::new(py, output.seed_fixtures)?.into_any(),
            ),
            (
                "dbt_ref_fixture_names",
                PyTuple::new(py, output.dbt_refs)?.into_any(),
            ),
            (
                "function_deps",
                PyTuple::new(py, KeyCache::new(py)?.keys(&output.functions)?)?.into_any(),
            ),
        ],
    )?;
    let mut warnings: Vec<Bound<'py, PyAny>> = Vec::new();
    for (message, coded) in output.warnings {
        let mut values = vec![
            ("model_name", py.None().into_bound(py)),
            (
                "severity",
                imported(py, TYPES, "WarningSeverity")?.getattr("ERROR")?,
            ),
            ("message", string(py, &message)),
        ];
        if coded {
            values.push((
                "code",
                imported(py, CONSTANTS, "SCENARIO_PLAN_GRAPH_VALIDATION")?,
            ));
        }
        warnings.push(call_with(&imported(py, MODELS, "PlanWarning")?, &values)?);
    }
    Ok((plan, PyTuple::new(py, warnings)?))
}
