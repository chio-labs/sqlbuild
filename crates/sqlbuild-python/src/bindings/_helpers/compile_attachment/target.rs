//! The effective target, its namespace, and the shared project-local compile-cache directory.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::pyfunction;
use pyo3::types::{PyDict, PyDictMethods, PyString, PyTuple};

use crate::bindings::_helpers::compile_attachment::effective_config::project_vars;
use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::model_config::template_data::{early_model_templates, run_id};

const TARGET_NAME_MODULE: &str = "sqlbuild._native";
const TARGET_CONFIG_MODULE: &str = "sqlbuild._native";
const COMPILE_CONSTANTS_MODULE: &str = "sqlbuild.compiler.compile.constants";
const FRONTIER_CONSTANTS_MODULE: &str = "sqlbuild.compiler.frontier.constants";
const CACHE_DIRECTORY_MODULE: &str = "sqlbuild.compiler.frontier.main.compiler_cache_directory";
const DATABASE_KEY: &str = "database";
const SCHEMA_KEY: &str = "schema";

/// The selected target's name and merged config, or `(None, None)`.
fn resolved_target<'py>(
    discovered: &Bound<'py, PyAny>,
    selected_target: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let py: Python<'py> = discovered.py();
    let project_config: Bound<'py, PyAny> = discovered.getattr("project_config")?;
    let local_config: Bound<'py, PyAny> = discovered.getattr("local_config")?;
    let target_name: Bound<'py, PyAny> = call_with(
        &imported(py, TARGET_NAME_MODULE, "resolve_target_name")?,
        &[
            ("project_config", project_config.clone()),
            ("local_config", local_config.clone()),
            ("selected_target", selected_target.clone()),
        ],
    )?;
    if target_name.is_none() {
        return Ok((target_name, py.None().into_bound(py)));
    }
    let target_config: Bound<'py, PyAny> = call_with(
        &imported(py, TARGET_CONFIG_MODULE, "resolve_target_config")?,
        &[
            ("project_config", project_config),
            ("local_config", local_config),
            ("target_name", target_name.clone()),
        ],
    )?;
    Ok((target_name, target_config))
}

/// Resolve the effective target and shared project-local compile-cache directory.
#[pyfunction]
#[pyo3(signature = (*, discovered_inputs, selected_target, no_cache))]
pub(crate) fn build_compile_target_context<'py>(
    discovered_inputs: &Bound<'py, PyAny>,
    selected_target: &Bound<'py, PyAny>,
    no_cache: bool,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = discovered_inputs.py();
    let (target_name, target_config) = resolved_target(discovered_inputs, selected_target)?;
    let cache_dir: Bound<'py, PyAny> = compile_cache_root(
        &discovered_inputs.getattr("project_dir")?,
        &target_config,
        no_cache,
    )?;
    PyTuple::new(py, [target_name, target_config, cache_dir])
}

/// The shared compile-cache directory, or `None` when caching is disabled.
fn compile_cache_root<'py>(
    project_dir: &Bound<'py, PyAny>,
    target_config: &Bound<'py, PyAny>,
    no_cache: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project_dir.py();
    let constant = |name: &str| imported(py, COMPILE_CONSTANTS_MODULE, name);
    let disabled_value: String = constant("COMPILE_CACHE_DISABLE_VALUE")?.extract()?;
    let disable_env: String = constant("COMPILE_CACHE_DISABLE_ENV_VAR")?.extract()?;
    let disabled: bool = py
        .import("os")?
        .getattr("environ")?
        .call_method1("get", (disable_env,))?
        .extract::<Option<String>>()?
        .is_some_and(|value| value == disabled_value);
    if no_cache
        || project_dir.is_none()
        || (!target_config.is_none()
            && target_config
                .getattr("compile_cache")?
                .is(pyo3::types::PyBool::new(py, false)))
        || disabled
    {
        return Ok(py.None().into_bound(py));
    }
    let root: Bound<'py, PyAny> =
        imported(py, CACHE_DIRECTORY_MODULE, "compiler_cache_directory")?.call1((project_dir,))?;
    remove_retired_caches(&root)?;
    Ok(root)
}

/// Delete the fact and reference caches older releases kept under each retired cache root.
fn remove_retired_caches(root: &Bound<'_, PyAny>) -> PyResult<()> {
    let py: Python<'_> = root.py();
    let directory_name: String = imported(
        py,
        FRONTIER_CONSTANTS_MODULE,
        "COMPILER_CACHE_DIRECTORY_NAME",
    )?
    .extract()?;
    let names: [Bound<'_, PyAny>; 2] = [
        imported(
            py,
            COMPILE_CONSTANTS_MODULE,
            "RETIRED_FACT_CACHE_DIRECTORY_NAME",
        )?,
        imported(
            py,
            COMPILE_CONSTANTS_MODULE,
            "RETIRED_REFERENCE_CACHE_DIRECTORY_NAME",
        )?,
    ];
    let rmtree: Bound<'_, PyAny> = imported(py, "shutil", "rmtree")?;
    let ignore: Bound<'_, PyDict> = PyDict::new(py);
    ignore.set_item("ignore_errors", true)?;
    for suffix in imported(
        py,
        FRONTIER_CONSTANTS_MODULE,
        "RETIRED_CACHE_NAMESPACE_SUFFIXES",
    )?
    .try_iter()?
    {
        let suffix: String = suffix?.extract()?;
        for name in &names {
            let retired: Bound<'_, PyAny> = root
                .getattr("parent")?
                .div(format!("{directory_name}{suffix}"))?
                .div(name)?;
            if retired.call_method0("is_dir")?.is_truthy()? {
                rmtree.call((retired,), Some(&ignore))?;
            }
        }
    }
    Ok(())
}

/// `value if isinstance(value, str) and value else None`.
fn optional_string<'py>(
    value: Option<Bound<'py, PyAny>>,
    py: Python<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    Ok(match value {
        Some(value) if value.is_instance_of::<PyString>() && value.is_truthy()? => value,
        _ => py.None().into_bound(py),
    })
}

/// `first or second or third`.
fn first_truthy<'py>(values: [Bound<'py, PyAny>; 3]) -> PyResult<Bound<'py, PyAny>> {
    let [first, second, third] = values;
    if first.is_truthy()? {
        return Ok(first);
    }
    if second.is_truthy()? {
        return Ok(second);
    }
    Ok(third)
}

/// Resolve the target and its effective database/schema without compiling resources.
#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn build_effective_target_namespace<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "build_effective_target_namespace",
        options,
        (
            &[
                "discovered_inputs",
                "selected_target",
                "connection_database",
                "connection_schema",
                "default_database",
                "default_schema",
            ],
            &[],
        ),
    )?;
    let discovered_inputs: &Bound<'py, PyAny> = &arguments.value("discovered_inputs")?;
    let selected_target: &Bound<'py, PyAny> = &arguments.value("selected_target")?;
    let connection_database: Bound<'py, PyAny> = arguments.value("connection_database")?;
    let connection_schema: Bound<'py, PyAny> = arguments.value("connection_schema")?;
    let default_database: Bound<'py, PyAny> = arguments.value("default_database")?;
    let default_schema: Bound<'py, PyAny> = arguments.value("default_schema")?;
    let (target_name, target_config) = resolved_target(discovered_inputs, selected_target)?;
    let effective_vars: Bound<'py, PyAny> = project_vars(discovered_inputs, &target_config)?;
    let target_value = |key: &str| -> PyResult<Bound<'py, PyAny>> {
        if target_config.is_none() {
            return Ok(py.None().into_bound(py));
        }
        target_config.getattr(key)
    };
    let values: Bound<'py, PyDict> = PyDict::new(py);
    values.set_item(
        DATABASE_KEY,
        first_truthy([
            target_value(DATABASE_KEY)?,
            connection_database,
            default_database,
        ])?,
    )?;
    values.set_item(
        SCHEMA_KEY,
        first_truthy([target_value(SCHEMA_KEY)?, connection_schema, default_schema])?,
    )?;
    let run_id: Bound<'py, PyAny> = run_id(&py.None().into_bound(py))?;
    let resolved: Bound<'py, PyDict> =
        early_model_templates(values.as_any(), &effective_vars, (&target_name, &run_id))?
            .downcast_into()?;
    PyTuple::new(
        py,
        [
            target_name,
            target_config,
            optional_string(resolved.get_item(DATABASE_KEY)?, py)?,
            optional_string(resolved.get_item(SCHEMA_KEY)?, py)?,
        ],
    )
}
