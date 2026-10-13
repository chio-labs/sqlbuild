//! Adapter-aware target namespace validation of a compile.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyString, PyStringMethods};
use pyo3::{pyfunction, wrap_pyfunction};

use sqlbuild_analysis::assembly::target_checks::constants::{
    LOADER_COLLISION_CODE, MANAGED_WRITE_SCHEMA_CODE, MISSING_TARGET_PARTS_CODE,
    NAMED_TARGET_SCHEMA_CODE,
};
use sqlbuild_analysis::assembly::target_checks::errors::TargetError;
use sqlbuild_analysis::assembly::target_checks::main::explicit_write_schema::explicit_write_schema;
use sqlbuild_analysis::assembly::target_checks::main::first_shared_namespace::first_shared_namespace;
use sqlbuild_analysis::assembly::target_checks::main::missing_target_parts::missing_target_parts;
use sqlbuild_analysis::assembly::target_checks::main::target_error_message::target_error_message;
use sqlbuild_analysis::assembly::target_checks::models::{LoaderCollision, MissingParts};
use sqlbuild_core::text::main::python_strip::python_strip;

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported, keywords,
};

const PLANNER_EXCEPTIONS_MODULE: &str = "sqlbuild.compiler.planner.exceptions";
const TARGET_NAME_MODULE: &str = "sqlbuild.spec.contracts.main.resolve_target_name";
const TARGET_CONFIG_MODULE: &str = "sqlbuild.spec.contracts.main.resolve_target_config";
const EFFECTIVE_RUNTIME_MODULE: &str = "sqlbuild.compiler.compile.main.effective_runtime";
const EFFECTIVE_CONFIG_MODULE: &str = "sqlbuild.compiler.compile.main.effective_config";
const EXPAND_TEMPLATE_MODULE: &str = "sqlbuild.compiler.compile.main.expand_template_data";
const SETTING_HELP_MODULE: &str = "sqlbuild.errors.setting_help.main.setting_help";
/// Connection settings that identify the warehouse two targets write to.
const CONNECTION_IDENTITY_KEYS: [&str; 7] = [
    "account",
    "host",
    "port",
    "project",
    "server",
    "server_hostname",
    "workspace_url",
];
/// Adapters whose execution needs every model and seed database and schema resolved.
const EXPLICIT_TARGET_ADAPTERS: [&str; 3] = ["snowflake", "bigquery", "databricks"];
const LOADER_NAMESPACE_LABEL: &str = "managed loader target namespace";
const DEFAULTS_HELP_PURPOSE: &str = "to set project-wide defaults";
const PROJECT_CONFIG_FILENAME: &str = "sqlbuild_project.toml";
const DEFAULTS_SECTION: &str = "defaults";

/// One optional `(database, schema)` namespace.
type Namespace = (Option<String>, Option<String>);
/// A target's sorted connection identity and the namespaces its managed sources write.
type TargetNamespaces = (Vec<(String, String)>, Vec<Namespace>);

/// A `PlannerInputError` with `message`, `code` and optional `help`.
fn planner_error(py: Python<'_>, message: String, code: &str, help: Option<String>) -> PyErr {
    let raised: PyResult<Bound<'_, PyAny>> = (|| {
        imported(py, PLANNER_EXCEPTIONS_MODULE, "PlannerInputError")?.call(
            (message,),
            Some(&keywords(
                py,
                &[
                    ("code", PyString::new(py, code).into_any()),
                    (
                        "help",
                        help.map_or_else(
                            || py.None().into_bound(py),
                            |help| PyString::new(py, &help).into_any(),
                        ),
                    ),
                ],
            )?),
        )
    })();
    match raised {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

/// `value` as an optional string: `None`, or a `str`'s text.
fn optional_text(value: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if value.is_none() {
        return Ok(None);
    }
    Ok(Some(value.extract()?))
}

/// `value` when it is a `str`, else `None`.
fn text_or_none(value: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    match value.downcast::<PyString>() {
        Ok(text) => Ok(Some(text.to_cow()?.into_owned())),
        Err(_) => Ok(None),
    }
}

/// Require shared-warehouse named targets to choose a schema strategy.
#[pyfunction]
#[pyo3(signature = (**options))]
fn validate_named_target_schema_strategy<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> Result<(), PyErr> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "validate_named_target_schema_strategy",
        options,
        (&["discovered_inputs", "adapter", "selected_target"], &[]),
    )?;
    named_target_schema_strategy(
        &arguments.value("discovered_inputs")?,
        &arguments.value("adapter")?,
        &arguments.value("selected_target")?,
    )
}

/// `validate_named_target_schema_strategy` with its arguments.
pub(crate) fn named_target_schema_strategy(
    discovered: &Bound<'_, PyAny>,
    adapter: &Bound<'_, PyAny>,
    selected_target: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let py: Python<'_> = discovered.py();
    if adapter
        .getattr("allows_implicit_managed_write_schema")?
        .is_truthy()?
    {
        return Ok(());
    }
    let project_config: Bound<'_, PyAny> = discovered.getattr("project_config")?;
    let local_config: Bound<'_, PyAny> = discovered.getattr("local_config")?;
    let target_name: Bound<'_, PyAny> = call_with(
        &imported(py, TARGET_NAME_MODULE, "resolve_target_name")?,
        &[
            ("project_config", project_config.clone()),
            ("local_config", local_config.clone()),
            ("selected_target", selected_target.clone()),
        ],
    )?;
    if target_name.is_none() {
        return Ok(());
    }
    let target_config: Bound<'_, PyAny> = call_with(
        &imported(py, TARGET_CONFIG_MODULE, "resolve_target_config")?,
        &[
            ("project_config", project_config),
            ("local_config", local_config),
            ("target_name", target_name.clone()),
        ],
    )?;
    let schema: Option<String> = text_or_none(&target_config.getattr("schema")?)?;
    if schema.is_some_and(|schema| !python_strip(&schema).is_empty()) {
        return Ok(());
    }
    Err(planner_error(
        py,
        target_error_message(&TargetError::NamedTargetSchema(
            target_name.str()?.to_cow()?.into_owned(),
        )),
        NAMED_TARGET_SCHEMA_CODE,
        None,
    ))
}

/// Reject managed loader write namespaces shared by multiple targets.
#[pyfunction]
#[pyo3(signature = (**options))]
fn validate_managed_loader_target_isolation<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> Result<(), PyErr> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "validate_managed_loader_target_isolation",
        options,
        (&["discovered_inputs", "adapter"], &["resolved_connection"]),
    )?;
    managed_loader_target_isolation(
        &arguments.value("discovered_inputs")?,
        &arguments.value("adapter")?,
        &arguments.value("resolved_connection")?,
    )
}

/// `validate_managed_loader_target_isolation` with its arguments.
pub(crate) fn managed_loader_target_isolation(
    discovered: &Bound<'_, PyAny>,
    adapter: &Bound<'_, PyAny>,
    resolved_connection: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let py: Python<'_> = discovered.py();
    let mut managed_sources: Vec<Bound<'_, PyAny>> = Vec::new();
    for source_file in discovered.getattr("source_files")?.try_iter()? {
        for entry in source_file?.getattr("source_entries")?.try_iter()? {
            let entry: Bound<'_, PyAny> = entry?;
            if entry.getattr("managed")?.is_truthy()? {
                managed_sources.push(entry);
            }
        }
    }
    if managed_sources.is_empty() {
        return Ok(());
    }
    let project_config: Bound<'_, PyAny> = discovered.getattr("project_config")?;
    let local_config: Bound<'_, PyAny> = discovered.getattr("local_config")?;
    let mut target_names: Vec<String> = Vec::new();
    for config in [&project_config, &local_config] {
        for name in config.getattr("targets")?.try_iter()? {
            let name: String = name?.extract()?;
            if !target_names.contains(&name) {
                target_names.push(name);
            }
        }
    }
    target_names.sort();
    let mut targets: Vec<TargetNamespaces> = Vec::new();
    for target_name in &target_names {
        targets.push(target_namespaces(
            (discovered, adapter, resolved_connection),
            target_name,
            &managed_sources,
        )?);
    }
    for (index, left_target) in target_names.iter().enumerate() {
        for (offset, right_target) in target_names[index + 1..].iter().enumerate() {
            let (left, right) = (&targets[index], &targets[index + 1 + offset]);
            if left.0 != right.0 {
                continue;
            }
            let shared: Vec<Namespace> = left
                .1
                .iter()
                .filter(|namespace| right.1.contains(namespace))
                .cloned()
                .collect();
            let Some((database, schema)) = first_shared_namespace(&shared) else {
                continue;
            };
            return Err(planner_error(
                py,
                target_error_message(&TargetError::LoaderCollision(LoaderCollision {
                    left_target: left_target.clone(),
                    right_target: right_target.clone(),
                    database,
                    schema,
                })),
                LOADER_COLLISION_CODE,
                None,
            ));
        }
    }
    Ok(())
}

/// One target's connection identity and the namespaces its managed sources write.
fn target_namespaces(
    (discovered, adapter, resolved_connection): (
        &Bound<'_, PyAny>,
        &Bound<'_, PyAny>,
        &Bound<'_, PyAny>,
    ),
    target_name: &str,
    managed_sources: &[Bound<'_, PyAny>],
) -> PyResult<TargetNamespaces> {
    let py: Python<'_> = discovered.py();
    let name: Bound<'_, PyAny> = PyString::new(py, target_name).into_any();
    let target_config: Bound<'_, PyAny> = call_with(
        &imported(py, TARGET_CONFIG_MODULE, "resolve_target_config")?,
        &[
            ("project_config", discovered.getattr("project_config")?),
            ("local_config", discovered.getattr("local_config")?),
            ("target_name", name.clone()),
        ],
    )?;
    let runtime: Bound<'_, PyAny> = call_with(
        &imported(
            py,
            EFFECTIVE_RUNTIME_MODULE,
            "build_effective_runtime_config",
        )?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("selected_target", name.clone()),
        ],
    )?;
    let (_, effective_vars, _): (Bound<'_, PyAny>, Bound<'_, PyAny>, Bound<'_, PyAny>) =
        runtime.extract()?;
    let connection: Bound<'_, PyAny> = if resolved_connection.is_none() {
        call_with(
            &imported(
                py,
                EFFECTIVE_CONFIG_MODULE,
                "build_effective_connection_config",
            )?,
            &[
                ("discovered_inputs", discovered.clone()),
                ("selected_target", name),
            ],
        )?
    } else {
        resolved_connection.clone()
    };
    let mut identity: Vec<(String, String)> = Vec::new();
    for item in connection.call_method0("items")?.try_iter()? {
        let item: Bound<'_, PyAny> = item?;
        let key: Bound<'_, PyAny> = item.get_item(0)?;
        let Some(key) = text_or_none(&key)? else {
            continue;
        };
        if CONNECTION_IDENTITY_KEYS.contains(&key.as_str()) {
            identity.push((key, item.get_item(1)?.repr()?.to_cow()?.into_owned()));
        }
    }
    identity.sort();
    let mut namespaces: Vec<Namespace> = Vec::new();
    for source_entry in managed_sources {
        let namespace: Namespace = managed_source_namespace(
            source_entry,
            (&target_config, &connection, &effective_vars),
            adapter,
        )?;
        if !namespaces.contains(&namespace) {
            namespaces.push(namespace);
        }
    }
    Ok((identity, namespaces))
}

/// The first truthy value of `candidates`, else `fallback()`.
fn first_truthy<'py>(
    candidates: &[Bound<'py, PyAny>],
    fallback: impl FnOnce() -> PyResult<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    for candidate in candidates {
        if candidate.is_truthy()? {
            return Ok(candidate.clone());
        }
    }
    fallback()
}

/// `_managed_source_namespace`: the database and schema a managed source loads into.
fn managed_source_namespace(
    source_entry: &Bound<'_, PyAny>,
    (target_config, connection, effective_vars): (
        &Bound<'_, PyAny>,
        &Bound<'_, PyAny>,
        &Bound<'_, PyAny>,
    ),
    adapter: &Bound<'_, PyAny>,
) -> PyResult<Namespace> {
    let py: Python<'_> = source_entry.py();
    let database: Bound<'_, PyAny> = first_truthy(
        &[
            source_entry.getattr("database")?,
            target_config.getattr("database")?,
            connection.call_method1("get", ("database",))?,
        ],
        || adapter.call_method0("default_database"),
    )?;
    let schema: Bound<'_, PyAny> = first_truthy(
        &[
            source_entry.getattr("schema")?,
            target_config.getattr("loader_schema")?,
            target_config.getattr("schema")?,
            connection.call_method1("get", ("schema",))?,
        ],
        || adapter.call_method0("default_schema"),
    )?;
    let value: Bound<'_, PyDict> = PyDict::new(py);
    pyo3::types::PyDictMethods::set_item(&value, "database", database)?;
    pyo3::types::PyDictMethods::set_item(&value, "schema", schema)?;
    let false_value: Bound<'_, PyAny> = pyo3::types::PyBool::new(py, false).to_owned().into_any();
    let expanded: Bound<'_, PyAny> = call_with(
        &imported(py, EXPAND_TEMPLATE_MODULE, "expand_template_data")?,
        &[
            ("value", value.into_any()),
            ("variables", effective_vars.clone()),
            ("context_values", PyDict::new(py).into_any()),
            (
                "context_label",
                PyString::new(py, LOADER_NAMESPACE_LABEL).into_any(),
            ),
            ("allow_context", false_value.clone()),
            ("preserve_context_tokens", false_value.clone()),
            ("preserve_unknown_context", false_value),
        ],
    )?;
    let part = |key: &str| -> PyResult<Option<String>> {
        let value: Bound<'_, PyAny> = expanded.get_item(key)?;
        if value.is_none() {
            return Ok(None);
        }
        Ok(Some(value.str()?.to_cow()?.into_owned()))
    };
    Ok((part("database")?, part("schema")?))
}

/// Validate compiled model and seed locations for the effective adapter.
#[pyfunction]
#[pyo3(signature = (**options))]
fn validate_project_targets<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> Result<(), PyErr> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "validate_project_targets",
        options,
        (&["adapter_name", "project"], &[]),
    )?;
    project_targets(
        &arguments.value("adapter_name")?,
        &arguments.value("project")?,
    )
}

/// `validate_project_targets` with its arguments.
pub(crate) fn project_targets(
    adapter_name: &Bound<'_, PyAny>,
    project: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let name: Option<String> = text_or_none(adapter_name)?;
    if !name
        .as_deref()
        .is_some_and(|name| EXPLICIT_TARGET_ADAPTERS.contains(&name))
    {
        return Ok(());
    }
    let adapter_label: String = adapter_name.str()?.to_cow()?.into_owned();
    for (resource_kind, attribute) in [("model", "models"), ("seed", "seeds")] {
        let mut targets: Vec<(String, Bound<'_, PyAny>)> = Vec::new();
        for resource in project.getattr(attribute)?.try_iter()? {
            let resource: Bound<'_, PyAny> = resource?;
            let resource_name: String = resource.getattr("name")?.str()?.to_cow()?.into_owned();
            let destination: Bound<'_, PyAny> = resource.getattr("destination")?;
            match targets
                .iter_mut()
                .find(|(existing, _)| *existing == resource_name)
            {
                Some(entry) => entry.1 = destination,
                None => targets.push((resource_name, destination)),
            }
        }
        for (resource_name, target) in targets {
            required_target_parts((&adapter_label, resource_kind), resource_name, &target)?;
        }
    }
    Ok(())
}

/// Raise when `target` misses its database or schema.
fn required_target_parts(
    (adapter_name, resource_kind): (&str, &str),
    resource_name: String,
    target: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let py: Python<'_> = target.py();
    let database: Option<String> = optional_text(&target.getattr("database")?)?;
    let schema: Option<String> = optional_text(&target.getattr("schema")?)?;
    let missing: Vec<&str> = missing_target_parts(database.as_deref(), schema.as_deref());
    let Some(first) = missing.first() else {
        return Ok(());
    };
    let help: String = call_with(
        &imported(py, SETTING_HELP_MODULE, "setting_help")?,
        &[
            (
                "purpose",
                PyString::new(py, DEFAULTS_HELP_PURPOSE).into_any(),
            ),
            (
                "file_name",
                PyString::new(py, PROJECT_CONFIG_FILENAME).into_any(),
            ),
            ("section", PyString::new(py, DEFAULTS_SECTION).into_any()),
            ("key", PyString::new(py, first).into_any()),
            (
                "value",
                PyString::new(py, &format!("my_{first}")).into_any(),
            ),
        ],
    )?
    .extract()?;
    Err(planner_error(
        py,
        target_error_message(&TargetError::MissingParts(MissingParts {
            adapter_name: adapter_name.to_owned(),
            resource_kind: resource_kind.to_owned(),
            resource_name,
            database,
            schema,
        })),
        MISSING_TARGET_PARTS_CODE,
        Some(help),
    ))
}

/// Require an explicitly resolved physical schema for every managed warehouse write.
#[pyfunction]
#[pyo3(signature = (**options))]
fn validate_managed_write_schemas<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> Result<(), PyErr> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "validate_managed_write_schemas",
        options,
        (&["adapter", "project"], &[]),
    )?;
    managed_write_schemas(&arguments.value("adapter")?, &arguments.value("project")?)
}

/// `validate_managed_write_schemas` with its arguments.
pub(crate) fn managed_write_schemas(
    adapter: &Bound<'_, PyAny>,
    project: &Bound<'_, PyAny>,
) -> PyResult<()> {
    if adapter
        .getattr("allows_implicit_managed_write_schema")?
        .is_truthy()?
    {
        return Ok(());
    }
    let connection_schema: Option<String> = explicit_write_schema(
        text_or_none(
            &project
                .getattr("effective_connection")?
                .call_method1("get", ("schema",))?,
        )?
        .as_deref(),
    );
    for (label, attribute) in [
        ("Model", "models"),
        ("Seed", "seeds"),
        ("Function", "functions"),
    ] {
        for resource in project.getattr(attribute)?.try_iter()? {
            let resource: Bound<'_, PyAny> = resource?;
            managed_write_schema(
                &format!("{label} '{}'", resource.getattr("name")?.str()?.to_cow()?),
                &resource.getattr("destination")?.getattr("schema")?,
                connection_schema.as_deref(),
            )?;
        }
    }
    for source in project.getattr("sources")?.try_iter()? {
        let source: Bound<'_, PyAny> = source?;
        let entry: Bound<'_, PyAny> = source.getattr("source_entry")?;
        if !entry.getattr("managed")?.is_truthy()? {
            continue;
        }
        managed_write_schema(
            &format!(
                "Managed source '{}'",
                source.getattr("name")?.str()?.to_cow()?
            ),
            &entry.getattr("schema")?,
            connection_schema.as_deref(),
        )?;
    }
    Ok(())
}

/// Raise when neither the resource nor the connection names a physical write schema.
fn managed_write_schema(
    resource_label: &str,
    schema: &Bound<'_, PyAny>,
    connection_schema: Option<&str>,
) -> PyResult<()> {
    if explicit_write_schema(text_or_none(schema)?.as_deref()).is_some()
        || connection_schema.is_some()
    {
        return Ok(());
    }
    Err(planner_error(
        schema.py(),
        target_error_message(&TargetError::ManagedWriteSchema(resource_label.to_owned())),
        MANAGED_WRITE_SCHEMA_CODE,
        None,
    ))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(
        validate_named_target_schema_strategy,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        validate_managed_loader_target_isolation,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(validate_project_targets, module)?)?;
    module.add_function(wrap_pyfunction!(validate_managed_write_schemas, module)?)
}
