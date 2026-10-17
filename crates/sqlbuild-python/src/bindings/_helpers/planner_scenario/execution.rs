//! Assemble scenario execution plans through existing planner and adapter APIs.

use crate::bindings::_helpers::analysis::model_reads;
use crate::bindings::_helpers::compile_driver::python_calls::KeywordArguments;
use crate::bindings::_helpers::compile_driver::python_calls::keywords;
use crate::bindings::_helpers::compiled_project::loop_classes::by_attribute;
use crate::bindings::_helpers::compiled_project::records::compiled_model_record;
use crate::bindings::_helpers::planner_entries::model_entries::plan_model;
use crate::bindings::_helpers::planner_entries::models::ModelPlanContext;
use crate::bindings::_helpers::planner_identity::graph::build_execution_upstream_deps;
use crate::bindings::_helpers::planner_identity::graph::topologically_order_keys;
use crate::bindings::_helpers::planner_phases::objects::object;
use crate::bindings::_helpers::planner_resolution::locations::build_function_locations;
use crate::bindings::_helpers::planner_scenario::constants::SCENARIO_PLAN_INVALID_FIXTURE;
use crate::bindings::_helpers::planner_scenario::{
    entries::{function_entry, seed_entries},
    fixtures::{extract_fixtures, fixture_plans},
    models::SqlContext,
    sql::{required_target, resolve_model_dbt_refs, resolve_sql, source_label},
    values::{error, string},
};
use crate::bindings::_helpers::planner_strategy::fixture_completion::complete_fixtures as complete_relation_fixtures;
use crate::bindings::_helpers::planner_strategy::fixture_context::planning_context;
use crate::bindings::_helpers::records::construct::{enum_member, new_record, new_record_with};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::replaced_keywords;
use crate::bindings::_helpers::records::ids::RecordId;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python, pyfunction};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyFrozenSet, PyTuple};

#[pyfunction]
#[pyo3(signature = (**kwargs))]
pub(crate) fn build_scenario_execution_plan<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "build_scenario_execution_plan",
        kwargs,
        (
            &[
                "scenario",
                "project",
                "adapter",
                "graph_plan",
                "relation_plan",
                "source_lexical_syntax",
            ],
            &[
                "snapshot",
                "source_warehouse_columns",
                "sql_analysis_enabled",
            ],
        ),
    )?;
    let scenario = args.value("scenario")?;
    let project = args.value("project")?;
    let graph = args.value("graph_plan")?;
    let context = SqlContext {
        adapter: args.value("adapter")?,
        relations: args.value("relation_plan")?,
        syntax: args.value("source_lexical_syntax")?,
        label: source_label(&scenario)?,
    };
    let snapshot = args.value("snapshot")?;
    let snapshot = if snapshot.is_truthy()? {
        snapshot
    } else {
        new_record(py, RecordId::WarehouseSnapshot, (), None)?
    };
    let columns = args.value("source_warehouse_columns")?;
    let columns = if columns.is_truthy()? {
        columns
    } else {
        PyDict::new(py).into_any()
    };
    let analysis = args.value("sql_analysis_enabled")?;
    let analysis = if analysis.is_none() {
        true
    } else {
        analysis.is_truthy()?
    };
    let models = by_attribute(&native_field(&project, "models")?, "name")?;
    let functions = by_attribute(&native_field(&project, "functions")?, "key")?;
    let locations = build_function_locations(&native_field(&project, "functions")?)?.into_any();
    let upstream = build_execution_upstream_deps(&project)?.into_any();
    let ordered = object(py, topologically_order_keys(&upstream, None)?)?;
    let mut model_keys: Vec<Bound<'py, PyAny>> = Vec::new();
    for key in ordered.try_iter()? {
        let key = key?;
        if native_field(&key, "resource_type")?.eq("model")?
            && native_field(&graph, "model_names")?.contains(native_field(&key, "name")?)?
        {
            model_keys.push(key);
        }
    }
    let overrides = if analysis {
        complete_fixtures(&scenario, &project, (&context, &model_keys))?
    } else {
        py.None().into_bound(py)
    };
    let fixtures = fixture_plans(&scenario, &graph, &context, &overrides)?;
    let seeds = seed_entries(&project, &graph, &context.relations)?;
    let mut function_entries: Vec<Bound<'py, PyAny>> = Vec::new();
    for key in ordered.try_iter()? {
        let key = key?;
        if native_field(&graph, "function_deps")?.contains(&key)?
            && let Some(function) = functions.get_item(key)?
        {
            function_entries.push(function_entry(&function, &context, &locations, &columns)?);
        }
    }
    let mut entries: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut warnings: Vec<Bound<'py, PyAny>> = Vec::new();
    for key in model_keys {
        let model = models
            .get_item(native_field(&key, "name")?)?
            .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("scenario model"))?;
        let destination = required_target(
            &context.relations,
            "model_locations",
            &model_reads::model_name(&model)?,
            "model",
        )?;
        let query = resolve_model_dbt_refs(
            &model_reads::query_sql(&model)?.extract::<String>()?,
            &context.relations,
        )?;
        let record = compiled_model_record(&model)?;
        let changes = PyDict::new(py);
        changes.set_item("destination", destination)?;
        changes.set_item("query_sql", query)?;
        let model = replaced_keywords(&record, &changes)?;
        let model_context = model_context(&project, &context, (&models, &locations, &columns))?;
        let result = object(
            py,
            plan_model(
                py,
                Some(keywords(
                    py,
                    &[
                        ("model", model),
                        ("snapshot", snapshot.clone()),
                        ("adapter", context.adapter.clone()),
                        ("context", model_context),
                        (
                            "sql_analysis_enabled",
                            PyBool::new(py, analysis).to_owned().into_any(),
                        ),
                        (
                            "query_change_tracking",
                            PyBool::new(py, false).to_owned().into_any(),
                        ),
                        ("full_refresh", PyBool::new(py, true).to_owned().into_any()),
                        (
                            "cursor_overrides",
                            new_record(py, RecordId::CursorOverridePair, (), None)?,
                        ),
                    ],
                )?),
            )?,
        )?;
        entries.push(result.get_item(0)?);
        for warning in result.get_item(1)?.try_iter()? {
            warnings.push(warning?);
        }
    }
    let (expected, assertions) = expectations(&scenario, &context)?;
    let plan = new_record_with(
        py,
        RecordId::ScenarioExecutionPlan,
        &[
            ("key", native_field(&scenario, "key")?),
            ("name", native_field(&scenario, "name")?),
            ("graph_plan", graph),
            ("relation_plan", context.relations),
            ("fixture_plans", fixtures.into_any()),
            ("seed_entries", seeds.into_any()),
            (
                "function_entries",
                PyTuple::new(py, function_entries)?.into_any(),
            ),
            ("model_entries", PyTuple::new(py, entries)?.into_any()),
            ("hook_functions", native_field(&project, "hook_functions")?),
            ("expected_expectations", expected),
            ("assertion_expectations", assertions),
        ],
    )?;
    Ok(PyTuple::new(py, [plan, PyTuple::new(py, warnings)?.into_any()])?.into_any())
}

fn complete_fixtures<'py>(
    scenario: &Bound<'py, PyAny>,
    project: &Bound<'py, PyAny>,
    inputs: (&SqlContext<'py>, &[Bound<'py, PyAny>]),
) -> PyResult<Bound<'py, PyAny>> {
    let (context, keys) = inputs;
    let py = scenario.py();
    let mut groups: Vec<Bound<'py, PyTuple>> = Vec::new();
    for (kind, prefix) in [
        ("SOURCE", "__source__"),
        ("MODEL", "__ref__"),
        ("SEED", "__seed__"),
    ] {
        let kind = enum_member(py, RecordId::CompiledResourceType, kind)?;
        groups.push(PyTuple::new(
            py,
            [kind, extract_fixtures(scenario, prefix)?.into_any()],
        )?);
    }
    let names = keys
        .iter()
        .map(|key| native_field(key, "name"))
        .collect::<PyResult<Vec<_>>>()?;
    let names = names
        .iter()
        .map(|name| name.extract())
        .collect::<PyResult<Vec<String>>>()?;
    let planning = planning_context(project, None)?;
    let completion = complete_relation_fixtures(
        &planning,
        &context.adapter,
        (&names, PyTuple::new(py, groups)?.as_any()),
    )?;
    if !completion.diagnostics.is_empty() {
        let mut details: Vec<String> = Vec::new();
        for diagnostic in &completion.diagnostics {
            details.push(format!(
                "- {}",
                native_field(diagnostic, "message")?.extract::<String>()?
            ));
        }
        let name: String = native_field(scenario, "name")?.extract()?;
        return Err(error(
            py,
            &format!(
                "Scenario '{name}' has invalid relation fixtures in {}:\n{}",
                context.label,
                details.join("\n")
            ),
            SCENARIO_PLAN_INVALID_FIXTURE,
            None,
        )?);
    }
    Ok(completion.sql_by_key.into_any())
}

fn model_context<'py>(
    project: &Bound<'py, PyAny>,
    context: &SqlContext<'py>,
    inputs: (&Bound<'py, PyDict>, &Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let (models, locations, columns) = inputs;
    let py = project.py();
    let none = || py.None();
    Ok(Bound::new(
        py,
        ModelPlanContext {
            model_locations: native_field(&context.relations, "model_locations")?.unbind(),
            models_by_name: models.clone().into_any().unbind(),
            functions_by_name: by_attribute(&native_field(project, "functions")?, "name")?
                .into_any()
                .unbind(),
            seed_locations: native_field(&context.relations, "seed_locations")?.unbind(),
            function_locations: locations.clone().unbind(),
            source_map: native_field(&context.relations, "source_map")?.unbind(),
            source_warehouse_columns: columns.clone().unbind(),
            star_exclude_keyword: context
                .adapter
                .call_method0("star_exclude_keyword")?
                .unbind(),
            runtime_cursor_producer_names: PyFrozenSet::empty(py)?.into_any().unbind(),
            future_cursor_config: none(),
            start_cursor_config: none(),
            invocation_time: none(),
        },
    )?
    .into_any())
}

fn expectations<'py>(
    scenario: &Bound<'py, PyAny>,
    context: &SqlContext<'py>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let py = scenario.py();
    let mut expected: Vec<Bound<'py, PyAny>> = Vec::new();
    for cte in native_field(scenario, "expected_ctes")?.try_iter()? {
        let cte = cte?;
        let name: String = native_field(&cte, "name")?.extract()?;
        let name = name.strip_prefix("__expected__").unwrap_or(&name);
        let target = required_target(&context.relations, "model_locations", name, "model")?;
        let sql = resolve_sql(
            context,
            &native_field(&cte, "sql_body")?.extract::<String>()?,
            false,
        )?;
        expected.push(new_record_with(
            py,
            RecordId::ScenarioExpectedExpectationPlan,
            &[
                ("model_name", string(py, name)),
                ("actual_destination", target),
                ("expected_sql", string(py, &sql)),
            ],
        )?);
    }
    let mut assertions: Vec<Bound<'py, PyAny>> = Vec::new();
    for cte in native_field(scenario, "assertion_ctes")?.try_iter()? {
        let cte = cte?;
        let name: String = native_field(&cte, "name")?.extract()?;
        let sql = resolve_sql(
            context,
            &native_field(&cte, "sql_body")?.extract::<String>()?,
            false,
        )?;
        assertions.push(new_record_with(
            py,
            RecordId::ScenarioAssertionExpectationPlan,
            &[
                (
                    "name",
                    string(py, name.strip_prefix("__assert__").unwrap_or(&name)),
                ),
                ("sql", string(py, &sql)),
            ],
        )?);
    }
    Ok((
        PyTuple::new(py, expected)?.into_any(),
        PyTuple::new(py, assertions)?.into_any(),
    ))
}
