//! Synthetic loader records for sources declaring an ingestr or dlt integration loader.

use pyo3::IntoPyObject;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::PyTuple;
use sqlbuild_discovery::yaml_entries::main::integration_loader_name::integration_loader_name;

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};

const DISCOVERY_MODELS_MODULE: &str = "sqlbuild.compiler.discovery.models";
const DISCOVERY_TYPES_MODULE: &str = "sqlbuild.compiler.discovery.types";

/// One integration: its kind constant and the runtime module building its loader functions.
struct Integration {
    constants_module: &'static str,
    kind_constant: &'static str,
    loaders_module: &'static str,
    loader_factory: &'static str,
}

/// Integrations in loader order: every ingestr loader precedes every dlt loader.
const INTEGRATIONS: [Integration; 2] = [
    Integration {
        constants_module: "sqlbuild.integrations.ingestr.constants",
        kind_constant: "INGESTR_INTEGRATION_KIND",
        loaders_module: "sqlbuild.integrations.ingestr.main._loaders",
        loader_factory: "ingestr_loader_function",
    },
    Integration {
        constants_module: "sqlbuild.integrations.dlt.constants",
        kind_constant: "DLT_INTEGRATION_KIND",
        loaders_module: "sqlbuild.integrations.dlt.main._loaders",
        loader_factory: "dlt_loader_function",
    },
];

/// The external-connection `DiscoveredLoaderFunction` of every integration source, in file order.
pub(crate) fn integration_loader_functions<'py>(
    py: Python<'py>,
    source_files: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let record_class: Bound<'py, PyAny> =
        imported(py, DISCOVERY_MODELS_MODULE, "DiscoveredLoaderFunction")?;
    let external: Bound<'py, PyAny> =
        imported(py, DISCOVERY_TYPES_MODULE, "LoaderConnectionMode")?.getattr("EXTERNAL")?;
    let mut loaders: Vec<Bound<'py, PyAny>> = Vec::new();
    for integration in &INTEGRATIONS {
        let kind: String =
            imported(py, integration.constants_module, integration.kind_constant)?.extract()?;
        let factory: Bound<'py, PyAny> =
            imported(py, integration.loaders_module, integration.loader_factory)?;
        for source_file in source_files.try_iter()? {
            let source_file: Bound<'py, PyAny> = source_file?;
            for source_entry in source_file.getattr("source_entries")?.try_iter()? {
                let source_entry: Bound<'py, PyAny> = source_entry?;
                let declared: Bound<'py, PyAny> = source_entry.getattr("integration_loader")?;
                if declared.is_none() || declared.getattr("kind")?.extract::<String>()? != kind {
                    continue;
                }
                let name: String = integration_loader_name(
                    &kind,
                    &source_entry.getattr("name")?.extract::<String>()?,
                );
                let function: Bound<'py, PyAny> = call_with(
                    &factory,
                    &[
                        ("source_entry", source_entry),
                        ("name", name.clone().into_pyobject(py)?.into_any()),
                    ],
                )?;
                loaders.push(call_with(
                    &record_class,
                    &[
                        ("file_path", source_file.getattr("file_path")?),
                        ("relative_path", source_file.getattr("relative_path")?),
                        ("name", name.into_pyobject(py)?.into_any()),
                        ("function", function),
                        ("connection_mode", external.clone()),
                    ],
                )?);
            }
        }
    }
    Ok(PyTuple::new(py, loaders)?.into_any())
}
