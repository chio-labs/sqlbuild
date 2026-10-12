//! The static inventory of project macro modules, as Python's AST analysis produced it.

use crate::macro_modules::_helpers::project_analysis::{ProjectSources, project_inventory};
use crate::macro_modules::errors::MacroModuleParseError;
use crate::macro_modules::models::{MacroModuleInventory, MacroModuleSource};

/// Exports, faults and load plan of the modules, or the ruff failure on a CPython-valid source.
pub fn inventory_macro_modules(
    sources: &[MacroModuleSource],
) -> Result<MacroModuleInventory, MacroModuleParseError> {
    project_inventory(&ProjectSources::new(sources))
}
