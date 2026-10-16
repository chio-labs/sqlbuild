//! Assemble CLI scenario plans while retaining adapter and executor boundaries.

use crate::bindings::_helpers::analysis::model_reads;
use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, call_with};
use crate::bindings::_helpers::planner_scenario::constants::SCENARIO_PLAN_GRAPH_VALIDATION;
use crate::bindings::_helpers::planner_scenario::graph::plan_scenario_graph;
use crate::bindings::_helpers::planner_scenario::models::ScenarioRelations;
use crate::bindings::_helpers::planner_scenario::relations::build_scenario_relation_plan;
use crate::bindings::_helpers::planner_scenario::values::string;
use crate::bindings::_helpers::records::ids::{ErrorId, NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python, pyfunction};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};

#[pyfunction]
#[pyo3(signature = (**kwargs))]
pub(crate) fn build_cli_scenario_plan<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "build_cli_scenario_plan",
        kwargs,
        (
            &[
                "scenario",
                "pipeline_result",
                "adapter",
                "project_name",
                "source_lexical_syntax",
            ],
            &[],
        ),
    )?;
    let scenario = args.value("scenario")?;
    let project = args.value("pipeline_result")?.getattr("project")?;
    let adapter = args.value("adapter")?;
    let (graph, warnings) = plan_scenario_graph(&scenario, &project, true, None)?;
    raise_for_warnings(warnings.as_any())?;
    let hashes = call_with(
        &registry::native(py, NativeAttr::BuildScenarioHashIndex)?,
        &[
            ("project_name", args.value("project_name")?),
            ("scenarios", project.getattr("sql_scenarios")?),
            (
                "run_namespace",
                project.getattr("scenario")?.getattr("run_namespace")?,
            ),
        ],
    )?;
    let mut identities: Vec<Bound<'py, PyAny>> = Vec::new();
    for (field, kind) in [
        ("source_fixture_names", "SOURCE"),
        ("ref_fixture_names", "REF"),
        ("dbt_ref_fixture_names", "DBT_REF"),
        ("seed_names", "SEED"),
        ("model_names", "MODEL"),
    ] {
        for name in graph.getattr(field)?.try_iter()? {
            identities.push(call_with(
                &registry::class(py, RecordId::ScenarioArtifactIdentity)?,
                &[
                    (
                        "kind",
                        registry::class(py, RecordId::ScenarioArtifactKind)?.getattr(kind)?,
                    ),
                    ("logical_name", name?),
                ],
            )?);
        }
    }
    let map = call_with(
        &registry::native(py, NativeAttr::BuildScenarioRelationMap)?,
        &[
            ("scenario_name", scenario.getattr("name")?),
            ("hash_prefix", hashes.get_item(scenario.getattr("name")?)?),
            ("artifacts", PyTuple::new(py, identities)?.into_any()),
            (
                "identifier_limit",
                adapter.call_method0("maximum_identifier_length")?,
            ),
        ],
    )?;
    let (database, schema) = namespace(&project, &graph)?;
    let relations = build_scenario_relation_plan(&ScenarioRelations {
        project: project.clone(),
        graph_plan: graph.clone(),
        relation_map: map,
        render_qualified_name: adapter.getattr("render_qualified_name")?,
        database,
        schema,
    })?;
    let result = call_with(
        &registry::native(py, NativeAttr::BuildScenarioExecutionPlan)?,
        &[
            ("scenario", scenario),
            ("project", project),
            ("adapter", adapter),
            ("graph_plan", graph),
            ("relation_plan", relations),
            (
                "source_lexical_syntax",
                args.value("source_lexical_syntax")?,
            ),
        ],
    )?;
    raise_for_warnings(&result.get_item(1)?)?;
    result.get_item(0)
}

fn namespace<'py>(
    project: &Bound<'py, PyAny>,
    graph: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let py = project.py();
    let models = PyDict::new(py);
    for model in project.getattr("models")?.try_iter()? {
        let model = model?;
        models.set_item(model_reads::name_object(&model)?, model)?;
    }
    for field in ["target_model_names", "model_names"] {
        for name in graph.getattr(field)?.try_iter()? {
            if let Some(model) = models.get_item(name?)? {
                let destination = model_reads::destination(&model)?;
                return Ok((
                    destination.getattr("database")?,
                    destination.getattr("schema")?,
                ));
            }
        }
    }
    Ok((py.None().into_bound(py), py.None().into_bound(py)))
}

fn raise_for_warnings(warnings: &Bound<'_, PyAny>) -> PyResult<()> {
    let py = warnings.py();
    let severity = registry::class(py, RecordId::WarningSeverity)?.getattr("ERROR")?;
    let mut messages: Vec<String> = Vec::new();
    let mut code = None;
    for warning in warnings.try_iter()? {
        let warning = warning?;
        if warning.getattr("severity")?.eq(&severity)? {
            if code.is_none() {
                let value = warning.getattr("code")?;
                code = Some(if value.is_truthy()? {
                    value
                } else {
                    string(py, SCENARIO_PLAN_GRAPH_VALIDATION)
                });
            }
            messages.push(warning.getattr("message")?.extract::<String>()?);
        }
    }
    if let Some(code) = code {
        return Err(PyErr::from_value(call_with(
            &registry::error(py, ErrorId::PlannerInput)?,
            &[
                ("message", string(py, &messages.join("\n"))),
                ("code", code),
            ],
        )?));
    }
    Ok(())
}
