//! Requests, outcomes and output facts of `sqb rename` and `sqb mv`.

/// Terminal state of one refactoring command.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RefactorStatus {
    Applied,
    DryRun,
    Refused,
    CompileFailed,
}

impl RefactorStatus {
    /// The status as JSON output spells it.
    #[must_use]
    pub fn value(self) -> &'static str {
        match self {
            Self::Applied => "applied",
            Self::DryRun => "dry_run",
            Self::Refused => "refused",
            Self::CompileFailed => "compile_failed",
        }
    }
}

/// The CLI target of `sqb rename` or `sqb mv`.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct RefactorTargetRequest {
    pub is_move: bool,
    pub target: String,
    pub new_name: Option<String>,
    pub destination: Option<String>,
    pub cascade: bool,
}

/// One compile error of the edited project.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RefactorDiagnostic {
    pub code: String,
    pub message: String,
    /// The path in POSIX form.
    pub path: Option<String>,
    pub line: Option<i64>,
    /// Whether a project rule reported it, rather than syntax, binding or reference checks.
    pub rule: bool,
}

/// The project's rule failures before a refactoring, and how the edited project compares.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct BaselineComparison {
    /// Rule failures of the project before any edit.
    pub before: Vec<RefactorDiagnostic>,
    /// Rule failures of the edited project that were already there, unchanged or reduced.
    pub remaining: Vec<RefactorDiagnostic>,
    /// Rule failures of the project before that the edited project no longer has.
    pub resolved: Vec<RefactorDiagnostic>,
    /// Edited-project errors that block the write: non-rule errors and new or worse rule failures.
    pub blocking: Vec<RefactorDiagnostic>,
}

/// The one-step `sqb mv` for a rename refused only by the layer-folder rules.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LayerMove {
    pub new_name: String,
    pub folder: Option<String>,
    pub layer_folder: Option<String>,
    pub command: String,
}

/// The command-line words and optional `(path, contents)` pair file of `sqb mv` or `sqb rename`.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct PairArguments<'a> {
    /// Whether the pairs are `sqb mv` moves rather than `sqb rename` renames.
    pub is_move: bool,
    pub words: Vec<&'a str>,
    pub file: Option<(&'a str, &'a str)>,
}
