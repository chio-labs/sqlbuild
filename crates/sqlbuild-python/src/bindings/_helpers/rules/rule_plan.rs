//! Plan one rules run: the catalogue, selected rules, project slice and settings it evaluates.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyFrozenSet, PySet, PySetMethods, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, keywords};
use crate::bindings::_helpers::rules::catalogue::{
    references_custom_rules, resolved_ignore_selectors, rule_catalogue, select_rules,
    verify_custom_rules,
};
use crate::bindings::_helpers::rules::rule_run::freed_memory_released;

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

const NATIVE_MODULE: &str = "sqlbuild._native";
const CUSTOM_PAYLOADS_MODULE: &str = "sqlbuild.rule_engine._helpers.engine.custom_payloads";
const RULES_CONSTANTS_MODULE: &str = "sqlbuild.rule_engine.constants";
const COMPILE_TYPES_MODULE: &str = "sqlbuild.compiler.compile.types";
const DATACLASSES_MODULE: &str = "dataclasses";
const PATHLIB_MODULE: &str = "pathlib";

/// Build the catalogue and select the rules, project slice and settings one run evaluates.
#[pyfunction]
#[pyo3(signature = (**options))]
fn plan_rule_run<'py>(options: Option<&Bound<'py, PyDict>>) -> PyResult<Bound<'py, PyAny>> {
    let options = Request::new("plan_rule_run", options)?;
    let py: Python<'py> = options.py();
    let graph: Bound<'py, PyAny> = options.get("graph")?;
    let project: Bound<'py, PyAny> = graph.getattr("project")?;
    freed_memory_released(py);
    let effective_config: Bound<'py, PyAny> =
        resolved_ignore_selectors(&options.get("config")?, &project)?;
    let project_dir: Bound<'py, PyAny> = options.get("project_dir")?.call_method0("resolve")?;
    let include_custom: bool = references_custom_rules(&effective_config)?;
    let catalogue: Vec<Bound<'py, PyAny>> =
        rule_catalogue(&effective_config, &project_dir, include_custom)?;
    let catalogue_tuple: Bound<'py, PyTuple> = PyTuple::new(py, &catalogue)?;
    let custom_payloads: Bound<'py, PyAny> = call_with(
        &imported(py, CUSTOM_PAYLOADS_MODULE, "custom_rule_payloads")?,
        &[
            ("catalogue", catalogue_tuple.clone().into_any()),
            ("project_dir", project_dir.clone()),
        ],
    )?;
    let mut selected: Vec<Bound<'py, PyAny>> = select_rules(
        &catalogue,
        &effective_config,
        &project_dir,
        Some(custom_payloads.clone()),
    )?;
    let mut skipped_type_proof_rules: Vec<Bound<'py, PyAny>> = Vec::new();
    if options.get("no_sql_analysis")?.is_truthy()?
        || !project
            .getattr("settings")?
            .getattr("sql_analysis")?
            .is_truthy()?
    {
        let type_proof: Bound<'py, PyAny> =
            imported(py, RULES_CONSTANTS_MODULE, "TYPE_PROOF_RULE_CODES")?;
        let mut kept: Vec<Bound<'py, PyAny>> = Vec::with_capacity(selected.len());
        for rule in selected {
            let code: Bound<'py, PyAny> = rule.getattr("code")?;
            if type_proof.contains(&code)? {
                skipped_type_proof_rules.push(code);
            } else {
                kept.push(rule);
            }
        }
        selected = kept;
    }
    let mut custom_rules: Vec<Bound<'py, PyAny>> = Vec::new();
    for rule in &selected {
        if rule.getattr("custom")?.is_truthy()? {
            custom_rules.push(rule.clone());
        }
    }
    if !custom_rules.is_empty() {
        verify_custom_rules(&custom_rules, &project_dir)?;
    }
    let model_paths: Option<Bound<'py, PyFrozenSet>> =
        selected_model_paths(&graph, &options.get("selected_keys")?)?;
    let selected_project: Bound<'py, PyAny> = match &model_paths {
        None => project.clone(),
        Some(paths) => selected_models_project(&project, paths)?,
    };
    let mut codes: Vec<Bound<'py, PyAny>> = Vec::with_capacity(selected.len());
    for rule in &selected {
        codes.push(rule.getattr("code")?);
    }
    let selection_config: Bound<'py, PyAny> =
        selection_rules_config(&effective_config, model_paths.as_ref(), &selected_project)?;
    let selected_config: Bound<'py, PyAny> = imported(py, DATACLASSES_MODULE, "replace")?.call(
        (selection_config,),
        Some(&keywords(
            py,
            &[
                ("select", PyTuple::new(py, codes)?.into_any()),
                ("ignore", PyTuple::empty(py).into_any()),
            ],
        )?),
    )?;
    call_with(
        &imported(py, NATIVE_RECORDS_MODULE, "RuleRunPlan")?,
        &[
            ("effective_config", effective_config),
            ("project_dir", project_dir),
            ("catalogue", catalogue_tuple.into_any()),
            ("custom_payloads", custom_payloads),
            ("selected", PyTuple::new(py, selected)?.into_any()),
            (
                "skipped_type_proof_rules",
                PyTuple::new(py, skipped_type_proof_rules)?.into_any(),
            ),
            (
                "model_paths",
                model_paths.map_or_else(|| py.None().into_bound(py), |paths| paths.into_any()),
            ),
            ("project", selected_project),
            ("config", selected_config),
        ],
    )
}

/// The relative paths of the selected models, or `None` when the run evaluates every model.
fn selected_model_paths<'py>(
    graph: &Bound<'py, PyAny>,
    selected_keys: &Bound<'py, PyAny>,
) -> PyResult<Option<Bound<'py, PyFrozenSet>>> {
    let py: Python<'py> = graph.py();
    if selected_keys.is_none() {
        return Ok(None);
    }
    let model_type: Bound<'py, PyAny> =
        imported(py, COMPILE_TYPES_MODULE, "CompiledResourceType")?.getattr("MODEL")?;
    let names: Bound<'py, PySet> = PySet::empty(py)?;
    for key in selected_keys.try_iter()? {
        let key: Bound<'py, PyAny> = key?;
        if key.getattr("resource_type")?.is(&model_type) {
            names.add(key.getattr("name")?)?;
        }
    }
    let paths: Bound<'py, PySet> = PySet::empty(py)?;
    for model in graph.getattr("project")?.getattr("models")?.try_iter()? {
        let model: Bound<'py, PyAny> = model?;
        if names.contains(model.getattr("name")?)? {
            paths.add(model.getattr("relative_path")?.call_method0("as_posix")?)?;
        }
    }
    Ok(Some(PyFrozenSet::new(py, paths.iter())?))
}

/// `project` keeping only the models whose relative path is in `model_paths`.
fn selected_models_project<'py>(
    project: &Bound<'py, PyAny>,
    model_paths: &Bound<'py, PyFrozenSet>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.py();
    let mut models: Vec<Bound<'py, PyAny>> = Vec::new();
    for model in project.getattr("models")?.try_iter()? {
        let model: Bound<'py, PyAny> = model?;
        if model_paths.contains(model.getattr("relative_path")?.call_method0("as_posix")?)? {
            models.push(model);
        }
    }
    call_with(
        &imported(py, NATIVE_MODULE, "project_with")?,
        &[
            ("project", project.clone()),
            ("models", PyTuple::new(py, models)?.into_any()),
        ],
    )
}

/// `config` keeping only the exceptions that apply to the selected models.
fn selection_rules_config<'py>(
    config: &Bound<'py, PyAny>,
    model_paths: Option<&Bound<'py, PyFrozenSet>>,
    project: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = config.py();
    let Some(model_paths) = model_paths else {
        return Ok(config.clone());
    };
    let path_class: Bound<'py, PyAny> = imported(py, PATHLIB_MODULE, "Path")?;
    let model_names: Bound<'py, PySet> = PySet::empty(py)?;
    for model in project.getattr("models")?.try_iter()? {
        model_names.add(model?.getattr("name")?)?;
    }
    let mut rule_exceptions: Vec<Bound<'py, PyAny>> = Vec::new();
    for entry in config.getattr("rule_exceptions")?.try_iter()? {
        let entry: Bound<'py, PyAny> = entry?;
        let path: Bound<'py, PyAny> = path_class
            .call1((entry.getattr("path")?,))?
            .call_method0("as_posix")?;
        if model_paths.contains(path)? {
            rule_exceptions.push(entry);
        }
    }
    let mut graph_edge_exceptions: Vec<Bound<'py, PyAny>> = Vec::new();
    for entry in config.getattr("graph_edge_exceptions")?.try_iter()? {
        let entry: Bound<'py, PyAny> = entry?;
        if model_names.contains(entry.getattr("consumer")?)? {
            graph_edge_exceptions.push(entry);
        }
    }
    imported(py, DATACLASSES_MODULE, "replace")?.call(
        (config,),
        Some(&keywords(
            py,
            &[
                (
                    "rule_exceptions",
                    PyTuple::new(py, rule_exceptions)?.into_any(),
                ),
                (
                    "graph_edge_exceptions",
                    PyTuple::new(py, graph_edge_exceptions)?.into_any(),
                ),
            ],
        )?),
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(plan_rule_run, module)?)?;
    Ok(())
}
