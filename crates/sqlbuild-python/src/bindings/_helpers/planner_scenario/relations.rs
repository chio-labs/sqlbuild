//! Build scenario relation locations through adapter qualification callbacks.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::planner_scenario::constants::{REF, SOURCE};
use crate::bindings::_helpers::planner_scenario::values::{MODELS, error};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python, pyfunction};
use pyo3::types::{PyDict, PyDictMethods};

#[pyfunction]
#[pyo3(signature = (**kwargs))]
pub(crate) fn build_scenario_relation_plan<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "build_scenario_relation_plan",
        kwargs,
        (
            &[
                "project",
                "graph_plan",
                "relation_map",
                "render_qualified_name",
            ],
            &["database", "schema"],
        ),
    )?;
    let graph = args.value("graph_plan")?;
    let artifacts = PyDict::new(py);
    for artifact in args
        .value("relation_map")?
        .getattr("artifacts")?
        .try_iter()?
    {
        let artifact = artifact?;
        let identity = artifact.getattr("identity")?;
        artifacts.set_item(
            (identity.getattr("kind")?, identity.getattr("logical_name")?),
            artifact.getattr("physical_name")?,
        )?;
    }
    let sources = PyDict::new(py);
    for source in args.value("project")?.getattr("sources")?.try_iter()? {
        let source = source?;
        sources.set_item(source.getattr("name")?, source.getattr("source_entry")?)?;
    }
    let models = PyDict::new(py);
    let refs = PyDict::new(py);
    let source_fixtures = PyDict::new(py);
    let dbt_refs = PyDict::new(py);
    let seeds = PyDict::new(py);
    let seed_fixtures = PyDict::new(py);
    let source_map = PyDict::new(py);
    for (field, kind, locations) in [
        ("model_names", "model", &models),
        ("ref_fixture_names", "ref", &refs),
        ("source_fixture_names", "source", &source_fixtures),
        ("dbt_ref_fixture_names", "dbt_ref", &dbt_refs),
        ("seed_names", "seed", &seeds),
    ] {
        for name in graph.getattr(field)?.try_iter()? {
            let name: String = name?.extract()?;
            let target = target_for_artifact(&args, &artifacts, kind, &name)?;
            locations.set_item(&name, &target)?;
            if kind == REF {
                models.set_item(&name, &target)?;
            } else if kind == SOURCE {
                let entry = sources
                    .get_item(&name)?
                    .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(name.clone()))?;
                let changes = PyDict::new(py);
                for field in ["database", "schema"] {
                    changes.set_item(field, target.getattr(field)?)?;
                }
                changes.set_item("table", target.getattr("name")?)?;
                changes.set_item("expression", py.None())?;
                changes.set_item("type_enforcement", false)?;
                let replacement =
                    imported(py, "dataclasses", "replace")?.call((entry,), Some(&changes))?;
                source_map.set_item(&name, replacement)?;
            }
        }
    }
    for name in graph.getattr("seed_fixture_names")?.try_iter()? {
        let name: String = name?.extract()?;
        let Some(target) = seeds.get_item(&name)? else {
            return Err(error(
                py,
                &format!("Scenario relation plan is missing seed target '{name}'"),
                "SCENARIO_PLAN_MISSING_RELATION_TARGET",
                Some("This is likely a SQLBuild bug. Please file an issue with the scenario name."),
            )?);
        };
        seed_fixtures.set_item(name, target)?;
    }
    call_with(
        &imported(py, MODELS, "ScenarioRelationPlan")?,
        &[
            ("scenario_name", graph.getattr("name")?),
            ("relation_map", args.value("relation_map")?),
            ("model_locations", models.into_any()),
            ("seed_locations", seeds.into_any()),
            ("project_source_map", sources.into_any()),
            ("source_map", source_map.into_any()),
            ("source_fixture_locations", source_fixtures.into_any()),
            ("ref_fixture_locations", refs.into_any()),
            ("dbt_ref_fixture_locations", dbt_refs.into_any()),
            ("seed_fixture_locations", seed_fixtures.into_any()),
        ],
    )
}

fn target_for_artifact<'py>(
    args: &KeywordArguments<'py>,
    artifacts: &Bound<'py, PyDict>,
    kind: &str,
    name: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let py = artifacts.py();
    let Some(physical) = artifacts.get_item((kind, name))? else {
        return Err(error(
            py,
            &format!("Scenario relation map is missing {kind} artifact '{name}'"),
            "SCENARIO_PLAN_INTERNAL",
            Some("This is likely a SQLBuild bug. Please file an issue with the scenario name."),
        )?);
    };
    let database = args.value("database")?;
    let schema = args.value("schema")?;
    let qualified = call_with(
        &args.value("render_qualified_name")?,
        &[
            ("database", database.clone()),
            ("schema", schema.clone()),
            ("name", physical.clone()),
        ],
    )?;
    call_with(
        &imported(
            py,
            "sqlbuild.compiler.compile.models",
            "CompiledRelationLocation",
        )?,
        &[
            ("database", database),
            ("schema", schema),
            ("name", physical.clone()),
            (
                "qualified_name",
                if qualified.is_none() {
                    physical
                } else {
                    qualified
                },
            ),
        ],
    )
}
