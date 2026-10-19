//! A model's authored SQL texts and the located diagnostics read from them.

use crate::semantic_validation::models::Expansion;

/// A reported diagnostic's identity: an error repeating it at a known start is dropped.
#[derive(Debug, PartialEq, Eq, Hash)]
pub(crate) struct SeenDiagnostic {
    pub(crate) code: String,
    pub(crate) message: String,
    pub(crate) line: Option<usize>,
    pub(crate) column: Option<usize>,
}

/// The texts one model's binding diagnostics are mapped back through.
#[derive(Clone, Copy, Debug)]
pub struct BindingSource<'a> {
    /// The whole authored model file.
    pub authored: &'a str,
    /// The authored query below the header.
    pub query: &'a str,
    /// The SQL the binding pass validated.
    pub cleaned: &'a str,
    /// The authored expansion's expanded SQL and passes, when interpolation left the query as is.
    pub expansion: Option<(&'a str, &'a [Vec<Expansion>])>,
}

/// A diagnostic's authored span: start line and column, and its end when it has one.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AuthoredSpan {
    pub line: usize,
    pub column: usize,
    pub end_line: Option<usize>,
    pub end_column: Option<usize>,
}

/// One binding diagnostic as compile reports it for a model.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LocatedDiagnostic {
    pub code: String,
    pub message: String,
    pub severity: String,
    pub line: Option<usize>,
    pub column: Option<usize>,
    pub location: Option<AuthoredSpan>,
}
