use crate::macro_modules::main::inventory_macro_modules::inventory_macro_modules;
use crate::macro_modules::models::{MacroModulePath, MacroModuleSource};
use crate::macro_modules::tests::test_types::{ExpectedExport, ExpectedModule, InventoryRows};
use crate::macro_modules::types::MacroScopeKind;

fn owned(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}

/// A global-scope module at `path` with `contents` that CPython accepted.
fn source((path, contents): (&str, &str)) -> MacroModuleSource {
    MacroModuleSource {
        relative_path: MacroModulePath {
            display: path.to_owned(),
            posix: path.to_owned(),
            parts: owned(&path.split('/').collect::<Vec<_>>()),
        },
        declaration_root: None,
        owning_path: None,
        scope_kind: MacroScopeKind::Global,
        contents: contents.to_owned(),
        syntax_error: None,
    }
}

/// The inventory of `sources` as plain rows, or the native parse failure's message.
pub(crate) fn inventory_rows(sources: &[(&str, &str)]) -> Result<InventoryRows, String> {
    let sources: Vec<MacroModuleSource> = sources.iter().copied().map(source).collect();
    let inventory = inventory_macro_modules(&sources).map_err(|error| error.to_string())?;
    Ok((
        inventory
            .exports
            .into_iter()
            .map(|export| {
                (
                    export.name,
                    export.file_index,
                    export.parameters,
                    export.line,
                    export.dependencies,
                )
            })
            .collect(),
        inventory
            .faults
            .into_iter()
            .map(|fault| (fault.file_index, fault.message))
            .collect(),
        inventory.modules.map(|modules| {
            modules
                .into_iter()
                .map(|module| {
                    (
                        module.file_index,
                        module.module_name,
                        module.module_dependencies,
                    )
                })
                .collect()
        }),
    ))
}

/// The expected rows of a test case.
pub(crate) fn expected_rows(
    exports: &[ExpectedExport],
    faults: &[(usize, &str)],
    modules: Option<&[ExpectedModule]>,
) -> InventoryRows {
    (
        exports
            .iter()
            .map(|(name, file, parameters, line, dependencies)| {
                (
                    (*name).to_owned(),
                    *file,
                    owned(parameters),
                    *line,
                    owned(dependencies),
                )
            })
            .collect(),
        faults
            .iter()
            .map(|(file, message)| (*file, (*message).to_owned()))
            .collect(),
        modules.map(|modules| {
            modules
                .iter()
                .map(|(file, name, dependencies)| (*file, (*name).to_owned(), owned(dependencies)))
                .collect()
        }),
    )
}
