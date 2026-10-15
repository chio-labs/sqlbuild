//! Project discovery: configuration, declaration files and imported project Python, validated.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyCFunction, PyDict, PySet, PySetMethods, PyTuple};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::config_validation::{
    ProjectConfiguration, reject_invalid_project_configuration,
};
use crate::bindings::_helpers::compile_driver::integration_loaders::integration_loader_functions;
use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported, keywords, within,
};
use crate::bindings::_helpers::discovery::declaration_records::{
    discover_adapter_file, discover_audit_files, discover_constant_files, discover_enum_files,
    discover_macro_files, discover_model_schema_files, discover_seed_files,
    discover_sql_function_files, discover_sql_hook_files, retained_discovery_session,
};
use crate::bindings::_helpers::discovery::model_records::{
    ModelFileSelection, discovered_model_files,
};
use crate::bindings::_helpers::discovery::python_function_files::discover_python_function_files;
use crate::bindings::_helpers::discovery::python_paths::reject_unsupported_python_paths;
use crate::bindings::_helpers::discovery::snapshot::in_snapshot;
use crate::bindings::_helpers::discovery::sql_test_records::{
    discover_scenario_files, discover_test_files,
};
use crate::bindings::_helpers::discovery::yaml_records::{
    discover_schema_files, discover_source_files,
};
use crate::bindings::_helpers::event_exporting::scope::configure_discovered_event_exporters;

const FRONTIER_MODULE: &str = "sqlbuild._native";
const FRONTIER_TYPES_MODULE: &str = "sqlbuild._native";
const LIFECYCLE_MODULE: &str = "sqlbuild.runtime.observability.classes.operation_lifecycle";
const VALIDATION_MODULE: &str = "sqlbuild.compiler.discovery._helpers.validation.discovery";
const NATIVE_MODULE: &str = "sqlbuild._native";
const SQL_ANALYSIS_SETTING_KEY: &str = "sql_analysis";
const FILESYSTEM_MODULE: &str = "sqlbuild._native";
const SINKS_MODULE: &str = "sqlbuild.compiler.discovery._helpers.filesystem.command_output_sinks";
const DISCOVERY_MODELS_MODULE: &str = "sqlbuild._native";

/// Declaration file collections counted into the declaration-parse lifecycle, in field order.
const DECLARATION_COLLECTIONS: [&str; 14] = [
    "source_files",
    "model_files",
    "enum_files",
    "constant_files",
    "model_schema_files",
    "sql_function_files",
    "sql_hook_files",
    "python_function_files",
    "schema_files",
    "seed_files",
    "test_files",
    "scenario_files",
    "audit_files",
    "macro_files",
];

/// A native discoverer that takes only `project_dir`.
type FileDiscoverer = for<'py> fn(&Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>>;

/// Early discoverers by result field, in their original order.
const FILE_DISCOVERERS: [(&str, FileDiscoverer); 14] = [
    ("enum_files", |dir| {
        Ok(discover_enum_files(dir, None, false)?.into_any())
    }),
    ("constant_files", |dir| {
        Ok(discover_constant_files(dir, None, false)?.into_any())
    }),
    ("model_schema_files", |dir| {
        Ok(discover_model_schema_files(dir, None)?.into_any())
    }),
    ("sql_function_files", |dir| {
        Ok(discover_sql_function_files(dir, None)?.into_any())
    }),
    ("sql_hook_files", |dir| {
        Ok(discover_sql_hook_files(dir, None)?.into_any())
    }),
    ("python_function_files", |dir| {
        Ok(discover_python_function_files(dir)?.into_any())
    }),
    ("schema_files", |dir| {
        Ok(discover_schema_files(dir)?.into_any())
    }),
    ("seed_files", |dir| Ok(discover_seed_files(dir)?.into_any())),
    ("test_files", |dir| {
        Ok(discover_test_files(dir, None, None)?.into_any())
    }),
    ("scenario_files", |dir| {
        Ok(discover_scenario_files(dir, None)?.into_any())
    }),
    ("audit_files", |dir| {
        Ok(discover_audit_files(dir, None)?.into_any())
    }),
    ("macro_files", |dir| {
        Ok(discover_macro_files(dir, false)?.into_any())
    }),
    ("adapter_file", discover_adapter_file),
    ("native_session", retained_discovery_session),
];

/// Discoverers of imported project Python that take `project_dir` and `providers`.
const PYTHON_DISCOVERERS: [(&str, &str, &str); 5] = [
    (
        "python_nodes",
        FILESYSTEM_MODULE,
        "discover_python_node_functions",
    ),
    (
        "materialization_files",
        FILESYSTEM_MODULE,
        "discover_materialization_files",
    ),
    (
        "hook_functions",
        FILESYSTEM_MODULE,
        "discover_hook_functions",
    ),
    (
        "event_exporters",
        FILESYSTEM_MODULE,
        "discover_event_exporter_functions",
    ),
    (
        "command_output_sinks",
        SINKS_MODULE,
        "discover_command_output_sink_functions",
    ),
];

/// Python node groups whose relative paths count as imported project Python.
const PYTHON_NODE_GROUPS: [&str; 5] = ["loaders", "tasks", "assets", "checks", "audit_factories"];

/// `OperationLifecycle(operation_kind="project", operation_name=name)`.
fn lifecycle<'py>(py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    call_with(
        &imported(py, LIFECYCLE_MODULE, "OperationLifecycle")?,
        &[
            ("operation_kind", "project".into_pyobject(py)?.into_any()),
            ("operation_name", name.into_pyobject(py)?.into_any()),
        ],
    )
}

/// The keyword arguments of one discovery, kept for the frontier stage.
struct DiscoveryRequest {
    project_dir: Py<PyAny>,
    sql_analysis_enabled_override: Py<PyAny>,
    extract_output_column_locations: bool,
}

/// Load all raw project inputs from disk before semantic resolution.
#[pyfunction]
#[pyo3(signature = (**options))]
fn discover_project_inputs<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "discover_project_inputs",
        options,
        (
            &["project_dir"],
            &[
                "sql_analysis_enabled_override",
                "extract_output_column_locations",
            ],
        ),
    )?;
    let request: DiscoveryRequest = DiscoveryRequest {
        project_dir: arguments.value("project_dir")?.unbind(),
        sql_analysis_enabled_override: arguments.value("sql_analysis_enabled_override")?.unbind(),
        extract_output_column_locations: !arguments.passed("extract_output_column_locations")?
            || arguments.flag("extract_output_column_locations")?,
    };
    within(&lifecycle(py, "project_discovery")?, |_| {
        let stage: Bound<'py, PyCFunction> = PyCFunction::new_closure(
            py,
            None,
            None,
            move |arguments: &Bound<'_, PyTuple>, _: Option<&Bound<'_, PyDict>>| {
                let py: Python<'_> = arguments.py();
                within(&lifecycle(py, "discovery_project_assembly")?, |_| {
                    assembled_inputs(py, &request)
                })
                .map(Bound::unbind)
            },
        )?;
        call_with(
            &imported(py, FRONTIER_MODULE, "compile_frontier")?,
            &[
                (
                    "until",
                    imported(py, FRONTIER_TYPES_MODULE, "CompilerStage")?
                        .getattr("DISCOVERED_PROJECT_INPUTS")?,
                ),
                ("python_stage", stage.into_any()),
            ],
        )
    })
}

/// `_assemble_discovered_project_inputs`: configuration, its checks, discovery and validation.
fn assembled_inputs<'py>(
    py: Python<'py>,
    request: &DiscoveryRequest,
) -> PyResult<Bound<'py, PyAny>> {
    let project_dir: &Bound<'py, PyAny> = request.project_dir.bind(py);
    let project_config: Bound<'py, PyAny> =
        imported(py, NATIVE_MODULE, "load_project_config_file")?.call1((project_dir,))?;
    let local_config: Bound<'py, PyAny> =
        imported(py, NATIVE_MODULE, "load_local_config_file")?.call1((project_dir,))?;
    reject_invalid_project_configuration(&ProjectConfiguration {
        project_dir,
        project_config: &project_config,
        local_config: &local_config,
    })?;
    reject_unsupported_python_paths(project_dir)?;
    let sql_analysis_override: &Bound<'py, PyAny> = request.sql_analysis_enabled_override.bind(py);
    let sql_analysis_enabled: Bound<'py, PyAny> = if !sql_analysis_override.is_none() {
        sql_analysis_override.clone()
    } else if local_config
        .getattr("setting_overrides")?
        .contains(SQL_ANALYSIS_SETTING_KEY)?
    {
        local_config.getattr("settings")?.getattr("sql_analysis")?
    } else {
        project_config
            .getattr("settings")?
            .getattr("sql_analysis")?
    };
    let discovered: Bound<'py, PyAny> = discovered_inputs(
        py,
        (project_dir, &project_config, &local_config),
        (
            sql_analysis_enabled.is_truthy()?,
            request.extract_output_column_locations,
        ),
    )?;
    imported(py, VALIDATION_MODULE, "validate_discovered_inputs")?.call1((&discovered,))?;
    configure_discovered_event_exporters(&discovered)?;
    Ok(discovered)
}

/// Discover all project files and functions into one inputs bundle.
#[pyfunction]
#[pyo3(signature = (**options))]
fn build_discovered_project_inputs<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "build_discovered_project_inputs",
        options,
        (
            &[
                "project_dir",
                "project_config",
                "local_config",
                "sql_analysis_enabled",
            ],
            &["extract_output_column_locations"],
        ),
    )?;
    discovered_inputs(
        py,
        (
            &arguments.value("project_dir")?,
            &arguments.value("project_config")?,
            &arguments.value("local_config")?,
        ),
        (
            arguments.flag("sql_analysis_enabled")?,
            !arguments.passed("extract_output_column_locations")?
                || arguments.flag("extract_output_column_locations")?,
        ),
    )
}

/// `build_discovered_project_inputs` for a loaded configuration.
fn discovered_inputs<'py>(
    py: Python<'py>,
    (project_dir, project_config, local_config): (
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
    ),
    flags: (bool, bool),
) -> PyResult<Bound<'py, PyAny>> {
    let declarations: Bound<'py, PyDict> = within(
        &lifecycle(py, "discovery_declaration_parse")?,
        |declaration_lifecycle| {
            let declarations: Bound<'py, PyDict> = declaration_files(project_dir, flags)?;
            let mut item_count: usize = 0;
            for field in DECLARATION_COLLECTIONS {
                item_count += declarations.as_any().get_item(field)?.len()?;
            }
            item_count += usize::from(!declarations.as_any().get_item("adapter_file")?.is_none());
            completed(declaration_lifecycle, item_count)?;
            Ok(declarations)
        },
    )?;
    let python: Bound<'py, PyDict> = within(
        &lifecycle(py, "discovery_python_import")?,
        |python_lifecycle| {
            let python: Bound<'py, PyDict> = imported_python(project_dir)?;
            completed(python_lifecycle, imported_python_paths(&python)?)?;
            Ok(python)
        },
    )?;
    project_inputs(
        (project_dir, project_config, local_config),
        &declarations,
        &python,
    )
}

/// Report a lifecycle's completion with its item count.
fn completed(lifecycle: &Bound<'_, PyAny>, item_count: usize) -> PyResult<()> {
    let py: Python<'_> = lifecycle.py();
    let metadata: Bound<'_, PyDict> = keywords(
        py,
        &[("item_count", item_count.into_pyobject(py)?.into_any())],
    )?;
    call_with(
        &lifecycle.getattr("completed")?,
        &[("metadata", metadata.into_any())],
    )?;
    Ok(())
}

/// `_discover_declaration_files`: every declaration file under one directory snapshot.
fn declaration_files<'py>(
    project_dir: &Bound<'py, PyAny>,
    (sql_analysis_enabled, extract_output_column_locations): (bool, bool),
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = project_dir.py();
    in_snapshot(project_dir, || {
        let files: Bound<'py, PyDict> = PyDict::new(py);
        files.set_item("source_files", discover_source_files(project_dir, None)?)?;
        files.set_item(
            "model_files",
            discovered_model_files(
                project_dir,
                (sql_analysis_enabled, extract_output_column_locations),
                ModelFileSelection {
                    selected_model_names: None,
                    on_fault: None,
                },
            )?,
        )?;
        for (field, discover) in FILE_DISCOVERERS {
            files.set_item(field, discover(project_dir)?)?;
        }
        Ok(files)
    })
}

/// Providers, then every kind of imported project Python that may use them.
fn imported_python<'py>(project_dir: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = project_dir.py();
    let providers: Bound<'py, PyAny> = call_with(
        &imported(py, FILESYSTEM_MODULE, "discover_provider_classes")?,
        &[("project_dir", project_dir.clone())],
    )?;
    let python: Bound<'py, PyDict> = PyDict::new(py);
    python.set_item("providers", &providers)?;
    for (field, module, name) in PYTHON_DISCOVERERS {
        python.set_item(
            field,
            call_with(
                &imported(py, module, name)?,
                &[
                    ("project_dir", project_dir.clone()),
                    ("providers", providers.clone()),
                ],
            )?,
        )?;
    }
    Ok(python)
}

/// How many distinct project Python files the imported discoveries came from.
fn imported_python_paths(python: &Bound<'_, PyDict>) -> PyResult<usize> {
    let py: Python<'_> = python.py();
    let python: &Bound<'_, PyAny> = python.as_any();
    let paths: Bound<'_, PySet> = PySet::empty(py)?;
    let mut groups: Vec<Bound<'_, PyAny>> = vec![python.get_item("providers")?];
    let nodes: Bound<'_, PyAny> = python.get_item("python_nodes")?;
    for group in PYTHON_NODE_GROUPS {
        groups.push(nodes.getattr(group)?);
    }
    for field in [
        "materialization_files",
        "hook_functions",
        "event_exporters",
        "command_output_sinks",
    ] {
        groups.push(python.get_item(field)?);
    }
    for group in groups {
        for item in group.try_iter()? {
            paths.add(item?.getattr("relative_path")?)?;
        }
    }
    Ok(paths.len())
}

/// The `DiscoveredProjectInputs` of the discovered declarations and imported Python.
fn project_inputs<'py>(
    (project_dir, project_config, local_config): (
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
    ),
    declarations: &Bound<'py, PyDict>,
    python: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project_dir.py();
    let declarations: &Bound<'py, PyAny> = declarations.as_any();
    let python: &Bound<'py, PyAny> = python.as_any();
    let nodes: Bound<'py, PyAny> = python.get_item("python_nodes")?;
    let tuple_of = |group: &str| -> PyResult<Bound<'py, PyAny>> {
        Ok(PyTuple::new(
            py,
            nodes
                .getattr(group)?
                .try_iter()?
                .collect::<PyResult<Vec<_>>>()?,
        )?
        .into_any())
    };
    let source_files: Bound<'py, PyAny> = declarations.get_item("source_files")?;
    let integration_loaders: Bound<'py, PyAny> = integration_loader_functions(py, &source_files)?;
    let loader_functions: Bound<'py, PyAny> = tuple_of("loaders")?.add(integration_loaders)?;
    let mut fields: Vec<(&str, Bound<'py, PyAny>)> = vec![
        ("project_config", project_config.clone()),
        ("local_config", local_config.clone()),
        ("project_dir", project_dir.clone()),
    ];
    for field in [
        "model_files",
        "enum_files",
        "constant_files",
        "model_schema_files",
        "sql_function_files",
        "sql_hook_files",
        "python_function_files",
        "schema_files",
        "source_files",
        "seed_files",
        "test_files",
        "scenario_files",
        "audit_files",
        "macro_files",
    ] {
        fields.push((field, declarations.get_item(field)?));
    }
    fields.push((
        "materialization_files",
        python.get_item("materialization_files")?,
    ));
    fields.push(("loader_functions", loader_functions));
    fields.push(("task_functions", tuple_of("tasks")?));
    fields.push(("asset_functions", tuple_of("assets")?));
    fields.push(("check_functions", tuple_of("checks")?));
    fields.push(("audit_factories", tuple_of("audit_factories")?));
    for field in [
        "hook_functions",
        "event_exporters",
        "command_output_sinks",
        "providers",
    ] {
        fields.push((field, python.get_item(field)?));
    }
    fields.push(("adapter_file", declarations.get_item("adapter_file")?));
    fields.push(("native_session", declarations.get_item("native_session")?));
    call_with(
        &imported(py, DISCOVERY_MODELS_MODULE, "DiscoveredProjectInputs")?,
        &fields,
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(discover_project_inputs, module)?)?;
    module.add_function(wrap_pyfunction!(build_discovered_project_inputs, module)?)
}
