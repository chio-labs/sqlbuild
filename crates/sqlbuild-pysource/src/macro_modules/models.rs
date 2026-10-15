//! Project macro modules in, and their static inventory and load order out.

use crate::macro_modules::types::MacroScopeKind;

/// A module's `relative_path` as `str()`, `as_posix()` and `parts` render it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MacroModulePath {
    pub display: String,
    pub posix: String,
    pub parts: Vec<String>,
}

/// One discovered macro module and the outcome of CPython's parse of it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MacroModuleSource {
    pub relative_path: MacroModulePath,
    /// `declaration_root.parts`, when the module has one.
    pub declaration_root: Option<Vec<String>>,
    /// `owning_path.parts`, when the module has one.
    pub owning_path: Option<Vec<String>>,
    pub scope_kind: MacroScopeKind,
    pub contents: String,
    /// The compile error message of CPython's parse, when CPython rejected the source.
    pub syntax_error: Option<String>,
}

/// One exported macro: a public top-level function of a module.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MacroExport {
    pub name: String,
    /// Index of the defining module in the analysed sources.
    pub file_index: usize,
    pub parameters: Vec<String>,
    /// CPython's `lineno` of the `def`.
    pub line: usize,
    /// SHA-256 hex digest of the module's UTF-8 source.
    pub source_digest: String,
    /// Names of every exported macro the export calls, directly or through helpers.
    pub dependencies: Vec<String>,
}

/// One static fault and the module it is attributed to.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MacroFault {
    pub file_index: usize,
    pub message: String,
}

/// A module the loader executes, with the project modules it imports.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MacroModuleLoad {
    pub file_index: usize,
    pub module_name: String,
    pub module_dependencies: Vec<String>,
}

/// Exports and faults of every module, and the load plan when the whole project analysed cleanly.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct MacroModuleInventory {
    /// Collision-free exports sorted by name, then path.
    pub exports: Vec<MacroExport>,
    /// Faults in discovery order, the first being the error a load raises.
    pub faults: Vec<MacroFault>,
    /// Every module in discovery order, present only when the strict analysis passed.
    pub modules: Option<Vec<MacroModuleLoad>>,
}

/// One macro module to load: its module name, file path text, contents and module dependencies.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MacroModuleSpec {
    pub name: String,
    pub file_path: String,
    pub contents: String,
    pub dependencies: Vec<String>,
}

/// The synthetic package root, its packages shallowest first, and the module execution order.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MacroLoadPlan {
    pub root: String,
    pub packages: Vec<String>,
    pub order: Vec<String>,
}
