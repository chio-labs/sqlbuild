//! Provider classes and lifecycle-event sinks from imported providers/ and sinks/ modules.

use std::collections::HashSet;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::pyfunction;
use pyo3::types::{PyDict, PyDictMethods};

use crate::bindings::_helpers::compile_driver::input_reads::record_settings_class_read;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::contracts::resource_identities::validate_resource_identity;
use crate::bindings::_helpers::discovery::imported_modules::{
    ProjectDir, discovered, discovery_error, discovery_error_from, module_functions,
    provider_by_name, provider_usages, shim, tuple_of,
};
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::native_host::user_code::UserCodeHost;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::mapping_get_or;
use crate::bindings::_helpers::records::ids::{ErrorId, RecordId};

const PROVIDER_ERROR: ErrorId = ErrorId::ProviderDiscovery;
const SINK_ERROR: ErrorId = ErrorId::EventExporterDiscovery;
const PROVIDER_INPUT_ERROR: UserCodeHost = UserCodeHost::ProviderInputError;
const VALIDATION_ERROR: (&str, &str) = ("pydantic", "ValidationError");
const SINK_DEFINITION: UserCodeHost = UserCodeHost::GetLifecycleEventSinkDefinition;
const ROOT_LOCATION: &str = "<root>";
const DEFAULT_MESSAGE: &str = "invalid value";
const DEFAULT_ERROR_TYPE: &str = "validation_error";
const DEFAULT_SETTINGS_ERROR: &str = "invalid provider settings";

fn reject_invalid_identity(
    name: &Bound<'_, PyAny>,
    relative_path: &Bound<'_, PyAny>,
) -> PyResult<()> {
    validate_resource_identity(name.downcast()?, "provider", relative_path, false)
}

/// The provider's validated name, from its explicit `provider_name` or `name()`.
fn provider_name<'py>(
    provider_class: &Bound<'py, PyAny>,
    relative_path: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = provider_class.py();
    let explicit: Bound<'py, PyAny> = native_field(provider_class, "provider_name")?;
    if !explicit.is_none() {
        reject_invalid_identity(&explicit, relative_path)?;
    }
    let name: Bound<'py, PyAny> = match provider_class.call_method0("name") {
        Ok(name) => name,
        Err(error) => {
            let input_error: Bound<'py, PyAny> = host::entry(py, PROVIDER_INPUT_ERROR)?;
            if !error.value(py).is_instance(&input_error)? {
                return Err(error);
            }
            let message: String = format!(
                "Provider class {} in {} has an invalid provider name: {}",
                provider_class.getattr("__name__")?.str()?,
                relative_path.str()?,
                error.value(py)
            );
            return Err(discovery_error_from(py, (PROVIDER_ERROR, message), error));
        }
    };
    reject_invalid_identity(&name, relative_path)?;
    Ok(name)
}

/// `"<location>: <message> [<type>]"` per pydantic error, one per line.
fn validation_details(error: &Bound<'_, PyAny>) -> PyResult<String> {
    let py: Python<'_> = error.py();
    let options: Bound<'_, PyDict> = PyDict::new(py);
    options.set_item("include_input", false)?;
    let mut details: Vec<String> = Vec::new();
    for item in error
        .call_method("errors", (), Some(&options))?
        .try_iter()?
    {
        let item: Bound<'_, PyAny> = item?;
        let location: Bound<'_, PyAny> = mapping_get_or(&item, "loc", py.None())?;
        let location_text: String = if location.is_none() || !location.is_truthy()? {
            ROOT_LOCATION.to_owned()
        } else {
            location
                .try_iter()?
                .map(|part| part?.str()?.extract::<String>())
                .collect::<PyResult<Vec<String>>>()?
                .join(".")
        };
        let message: Bound<'_, PyAny> = mapping_get_or(&item, "msg", DEFAULT_MESSAGE)?;
        let error_type: Bound<'_, PyAny> = mapping_get_or(&item, "type", DEFAULT_ERROR_TYPE)?;
        details.push(format!(
            "{location_text}: {} [{}]",
            message.str()?,
            error_type.str()?
        ));
    }
    if details.is_empty() {
        return Ok(DEFAULT_SETTINGS_ERROR.to_owned());
    }
    Ok(details.join("\n"))
}

/// An instance of the provider class, reporting invalid settings with each field's error.
fn provider_instance<'py>(
    provider_class: &Bound<'py, PyAny>,
    (provider_name, relative_path): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = provider_class.py();
    provider_class.call0().or_else(|error| {
        let validation_error: Bound<'py, PyAny> =
            imported(py, VALIDATION_ERROR.0, VALIDATION_ERROR.1)?;
        if !error.value(py).is_instance(&validation_error)? {
            return Err(error);
        }
        let message: String = format!(
            "Provider '{}' in {} has invalid settings:\n{}",
            provider_name.str()?,
            relative_path.str()?,
            validation_details(error.value(py))?
        );
        Err(discovery_error_from(py, (PROVIDER_ERROR, message), error))
    })
}

/// Provider classes under providers/.
#[pyfunction]
#[pyo3(signature = (*, project_dir))]
pub(crate) fn discover_provider_classes<'py>(
    project_dir: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project_dir.py();
    let project = ProjectDir { path: project_dir };
    if let Some(cached) = project.cached_extensions()? {
        let providers: Bound<'py, PyAny> = cached.get_item(0)?;
        for provider in providers.try_iter()? {
            record_settings_class_read(&native_field(&provider?, "provider_class")?)?;
        }
        return Ok(providers);
    }
    if !project
        .child("providers")?
        .call_method0("is_dir")?
        .is_truthy()?
    {
        return tuple_of(py, Vec::new());
    }
    let mut providers: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut seen: Vec<(String, Bound<'py, PyAny>)> = Vec::new();
    for file_path in project.module_files("providers", true)? {
        let module: Bound<'py, PyAny> =
            project.load(UserCodeHost::LoadProviderModule, &file_path)?;
        let classes: Bound<'py, PyAny> =
            shim(py, UserCodeHost::ModuleProviderClasses)?.call1((&module,))?;
        for provider_class in classes.try_iter()? {
            let provider_class: Bound<'py, PyAny> = provider_class?;
            let relative_path: Bound<'py, PyAny> = project.relative(&file_path)?;
            let name: Bound<'py, PyAny> = provider_name(&provider_class, &relative_path)?;
            let name_text: String = name.extract()?;
            if let Some((_, existing)) = seen.iter().find(|(listed, _)| *listed == name_text) {
                return Err(discovery_error(
                    py,
                    PROVIDER_ERROR,
                    format!(
                        "Duplicate provider name '{name_text}' found in {} and {}",
                        project.relative_to(existing)?,
                        project.relative_to(&file_path)?
                    ),
                ));
            }
            seen.push((name_text, file_path.clone()));
            record_settings_class_read(&provider_class)?;
            let settings: Bound<'py, PyAny> =
                provider_instance(&provider_class, (&name, &relative_path))?;
            providers.push(discovered(
                py,
                RecordId::DiscoveredProvider,
                &[
                    ("file_path", file_path.clone()),
                    ("relative_path", relative_path),
                    ("name", name),
                    ("provider_class", provider_class),
                    ("settings", settings),
                ],
            )?);
        }
    }
    tuple_of(py, providers)
}

/// Sink modules imported and their lifecycle declarations collected, without providers.
#[pyfunction]
#[pyo3(signature = (*, project_dir))]
pub(crate) fn discover_event_exporter_declarations<'py>(
    project_dir: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project_dir.py();
    let project = ProjectDir { path: project_dir };
    if project
        .child("event_exporters")?
        .call_method0("exists")?
        .is_truthy()?
    {
        return Err(discovery_error(
            py,
            SINK_ERROR,
            "event_exporters/ was replaced by sinks/ and @lifecycle_event_sink".to_owned(),
        ));
    }
    if !project
        .child("sinks")?
        .call_method0("is_dir")?
        .is_truthy()?
    {
        return tuple_of(py, Vec::new());
    }
    let read_definition: Bound<'py, PyAny> = host::entry(py, SINK_DEFINITION)?;
    let mut declarations: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut seen: Vec<(String, Bound<'py, PyAny>)> = Vec::new();
    for file_path in project.module_files("sinks", true)? {
        let module: Bound<'py, PyAny> = project.load(UserCodeHost::LoadSinkModule, &file_path)?;
        let mut seen_functions: HashSet<usize> = HashSet::new();
        for function in module_functions(&module)? {
            if !seen_functions.insert(function.as_ptr() as usize) {
                continue;
            }
            let read: Bound<'py, PyAny> = read_definition.call1((&function,))?;
            if read.is_none() {
                continue;
            }
            let name: String = native_field(&read, "name")?.extract()?;
            if let Some((_, existing)) = seen.iter().find(|(listed, _)| *listed == name) {
                return Err(discovery_error(
                    py,
                    SINK_ERROR,
                    format!(
                        "Duplicate event exporter name '{name}' found in {} and {}",
                        project.relative_to(existing)?,
                        project.relative_to(&file_path)?
                    ),
                ));
            }
            let relative_path: Bound<'py, PyAny> = project.relative(&file_path)?;
            call_with(
                &shim(py, UserCodeHost::ValidateEventExporterSignature)?,
                &[
                    ("function", function.clone()),
                    ("exporter_name", native_field(&read, "name")?),
                    ("relative_path", relative_path.clone()),
                ],
            )?;
            seen.push((name, file_path.clone()));
            declarations.push(discovered(
                py,
                RecordId::DiscoveredEventExporterDeclaration,
                &[
                    ("file_path", file_path.clone()),
                    ("relative_path", relative_path),
                    ("name", native_field(&read, "name")?),
                    ("function", function.clone()),
                    ("event_kinds", native_field(&read, "event_kinds")?),
                    ("min_severity", native_field(&read, "min_severity")?),
                ],
            )?);
        }
    }
    tuple_of(py, declarations)
}

/// Provider parameters after the event, each naming a known provider of the right class.
fn exporter_provider_usages<'py>(
    declaration: &Bound<'py, PyAny>,
    (project, providers): (&ProjectDir<'py>, &Bound<'py, PyDict>),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.py();
    let function: Bound<'py, PyAny> = native_field(declaration, "function")?;
    let name: String = native_field(declaration, "name")?.extract()?;
    let relative_path: String = project
        .relative(&native_field(declaration, "file_path")?)?
        .str()?
        .extract()?;
    let empty: Bound<'py, PyAny> = imported(py, "inspect", "Parameter")?.getattr("empty")?;
    let annotations: Bound<'py, PyAny> =
        shim(py, UserCodeHost::ParameterAnnotations)?.call1((&function,))?;
    for (index, pair) in annotations.try_iter()?.enumerate() {
        if index == 0 {
            continue;
        }
        let (parameter, annotation): (String, Bound<'py, PyAny>) = pair?.extract()?;
        let Some(provider) = providers.get_item(&parameter)? else {
            return Err(discovery_error(
                py,
                SINK_ERROR,
                format!(
                    "Event exporter '{name}' in {relative_path} requires unknown provider '{parameter}'"
                ),
            ));
        };
        let provider_class: Bound<'py, PyAny> = native_field(&provider, "provider_class")?;
        if !annotation.is(&empty) && !annotation.is(&provider_class) {
            return Err(discovery_error(
                py,
                SINK_ERROR,
                format!(
                    "Event exporter '{name}' in {relative_path} provider parameter '{parameter}' must be unannotated or exactly {}",
                    provider_class.getattr("__name__")?.str()?
                ),
            ));
        }
    }
    provider_usages(&function, providers)
}

/// Declarations bound to the discovered project providers they name.
#[pyfunction]
#[pyo3(signature = (*, declarations, providers, project_dir))]
pub(crate) fn bind_event_exporter_declarations<'py>(
    declarations: Bound<'py, PyAny>,
    providers: Bound<'py, PyAny>,
    project_dir: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project_dir.py();
    let project = ProjectDir { path: project_dir };
    let providers: Bound<'py, PyDict> = provider_by_name(&providers)?;
    let mut bound: Vec<Bound<'py, PyAny>> = Vec::new();
    for declaration in declarations.try_iter()? {
        let declaration: Bound<'py, PyAny> = declaration?;
        let usages: Bound<'py, PyAny> =
            exporter_provider_usages(&declaration, (&project, &providers))?;
        let mut pairs: Vec<(&str, Bound<'py, PyAny>)> = Vec::new();
        for field in [
            "file_path",
            "relative_path",
            "name",
            "function",
            "event_kinds",
            "min_severity",
        ] {
            pairs.push((field, native_field(&declaration, field)?));
        }
        pairs.push(("provider_usages", usages));
        bound.push(discovered(py, RecordId::DiscoveredEventExporter, &pairs)?);
    }
    tuple_of(py, bound)
}

/// Validated lifecycle-event sink declarations under sinks/, bound to providers.
#[pyfunction]
#[pyo3(signature = (*, project_dir, providers = None))]
pub(crate) fn discover_event_exporter_functions<'py>(
    project_dir: Bound<'py, PyAny>,
    providers: Option<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project_dir.py();
    let project = ProjectDir {
        path: project_dir.clone(),
    };
    if let Some(cached) = project.cached_extensions()? {
        return cached.get_item(1);
    }
    let declarations: Bound<'py, PyAny> =
        discover_event_exporter_declarations(project_dir.clone())?;
    bind_event_exporter_declarations(
        declarations,
        providers.map_or_else(|| tuple_of(py, Vec::new()), Ok)?,
        project_dir,
    )
}
