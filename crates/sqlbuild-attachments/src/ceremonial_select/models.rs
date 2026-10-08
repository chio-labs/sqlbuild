//! Where a SQL test or scenario body omits its trailing ceremonial `SELECT 1`.

/// Python's answer, or a deferral where only Python's Unicode rules can decide.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum OmittedSelect {
    /// Insert `SELECT 1` at this code-point offset.
    At(usize),
    /// The body already ends correctly or is not a bare `WITH` statement.
    Absent,
    Deferred,
}
