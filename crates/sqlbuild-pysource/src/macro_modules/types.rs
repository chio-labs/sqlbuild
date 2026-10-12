//! The visibility tier of a macro module, as Python's `ScopeKind` names it.

/// Who may import a macro module's exported macros.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MacroScopeKind {
    Global,
    Inherited,
    Local,
    Private,
}
