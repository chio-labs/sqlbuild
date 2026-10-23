//! Python sources, module moves, and the import edits and refusals a move needs.

/// One project Python file: its project-relative POSIX path and its text.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PythonSource {
    pub path: String,
    pub contents: String,
}

/// One Python module file moving from one project-relative POSIX path to another.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ModuleMove {
    pub from: String,
    pub to: String,
}

/// One replacement in a Python file, in byte offsets of the file before any edit.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ImportEdit {
    pub path: String,
    pub start: usize,
    pub end: usize,
    pub replacement: String,
}

/// An import of a moved module that cannot be rewritten safely, and why.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ImportRefusal {
    pub path: String,
    /// The 1-based line.
    pub line: usize,
    /// The 1-based column in characters.
    pub column: usize,
    pub reason: String,
}

/// Every import edit and refusal module moves need, in file then source order.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ImportRewrites {
    pub edits: Vec<ImportEdit>,
    pub refusals: Vec<ImportRefusal>,
}
