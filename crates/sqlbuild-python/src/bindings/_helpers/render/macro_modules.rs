//! Static inventory of project macro modules for the Python macro loader, with the GIL released.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_pysource::macro_modules::main::inventory_macro_modules::inventory_macro_modules as inventory;
use sqlbuild_pysource::macro_modules::main::macro_load_plan::macro_load_plan;
use sqlbuild_pysource::macro_modules::models::{
    MacroExport, MacroFault, MacroModuleInventory, MacroModuleLoad, MacroModulePath,
    MacroModuleSource,
};
use sqlbuild_pysource::macro_modules::models::{MacroLoadPlan, MacroModuleSpec};
use sqlbuild_pysource::macro_modules::types::MacroScopeKind;

use crate::bindings::_helpers::boundary::panics::{NativeCompilerError, compiler_error};
use crate::bindings::types::CompilerDetach;

/// Path as `str`, `as_posix` and parts, root and owner parts, scope, source and CPython error.
type SourceRow = (
    String,
    String,
    Vec<String>,
    Option<Vec<String>>,
    Option<Vec<String>>,
    String,
    String,
    Option<String>,
);

/// `(name, file index, parameters, line, source digest, dependency macro names)`.
type ExportRow = (String, usize, Vec<String>, usize, String, Vec<String>);

/// `(file index, message)`.
type FaultRow = (usize, String);

/// `(file index, module name, imported project module names)`.
type ModuleRow = (usize, String, Vec<String>);

/// Export rows, fault rows and the load plan rows when the strict analysis passed.
type InventoryRows = (Vec<ExportRow>, Vec<FaultRow>, Option<Vec<ModuleRow>>);

/// The tier a `ScopeKind` value names; any other value sees nothing, like `PRIVATE`.
fn scope_kind_of(value: &str) -> MacroScopeKind {
    match value {
        "global" => MacroScopeKind::Global,
        "inherited" => MacroScopeKind::Inherited,
        "local" => MacroScopeKind::Local,
        _ => MacroScopeKind::Private,
    }
}

fn source(row: SourceRow) -> MacroModuleSource {
    let (display, posix, parts, declaration_root, owning_path, scope_kind, contents, syntax_error) =
        row;
    MacroModuleSource {
        relative_path: MacroModulePath {
            display,
            posix,
            parts,
        },
        declaration_root,
        owning_path,
        scope_kind: scope_kind_of(&scope_kind),
        contents,
        syntax_error,
    }
}

fn export_row(export: MacroExport) -> ExportRow {
    (
        export.name,
        export.file_index,
        export.parameters,
        export.line,
        export.source_digest,
        export.dependencies,
    )
}

fn fault_row(fault: MacroFault) -> FaultRow {
    (fault.file_index, fault.message)
}

fn module_row(module: MacroModuleLoad) -> ModuleRow {
    (
        module.file_index,
        module.module_name,
        module.module_dependencies,
    )
}

/// Exports, faults and, when the strict analysis passes, the load plan of the macro modules.
#[pyfunction]
pub(crate) fn inventory_macro_modules(
    py: Python<'_>,
    sources: Vec<SourceRow>,
) -> PyResult<InventoryRows> {
    let sources: Vec<MacroModuleSource> = sources.into_iter().map(source).collect();
    let MacroModuleInventory {
        exports,
        faults,
        modules,
    } = py
        .compiler_detach(|| Ok(inventory(&sources)))
        .map_err(compiler_error)?
        .map_err(|error| NativeCompilerError::new_err(error.to_string()))?;
    Ok((
        exports.into_iter().map(export_row).collect(),
        faults.into_iter().map(fault_row).collect(),
        modules.map(|modules| modules.into_iter().map(module_row).collect()),
    ))
}

/// `(synthetic root, packages shallowest first, module execution order)` of `(name, path, contents, dependencies)` rows.
#[pyfunction]
fn macro_module_load_plan(
    modules: Vec<(String, String, String, Vec<String>)>,
) -> (String, Vec<String>, Vec<String>) {
    let specs: Vec<MacroModuleSpec> = modules
        .into_iter()
        .map(
            |(name, file_path, contents, dependencies)| MacroModuleSpec {
                name,
                file_path,
                contents,
                dependencies,
            },
        )
        .collect();
    let MacroLoadPlan {
        root,
        packages,
        order,
    } = macro_load_plan(&specs);
    (root, packages, order)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(inventory_macro_modules, module)?)?;
    module.add_function(wrap_pyfunction!(macro_module_load_plan, module)?)?;
    Ok(())
}
