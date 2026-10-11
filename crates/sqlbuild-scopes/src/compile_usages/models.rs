//! The schema declarations and indexed records compile usage facts are read from.

use crate::scope_index::models::DeclaredScope;

/// The first indexed record of a named schema or enum, by its caller handle.
#[derive(Clone, Debug)]
pub struct NamedRecord {
    /// The caller's handle for this record, echoed in usages.
    pub handle: usize,
    pub path: String,
    pub declared: DeclaredScope,
    pub ownership_root: String,
}

/// One reusable schema declaration: its name, the schema it extends, and each column's type.
#[derive(Clone, Debug)]
pub struct SchemaDeclaration {
    pub name: String,
    pub extends: Option<String>,
    pub columns: Vec<(String, Option<String>)>,
}

/// An S006 diagnostic: its report key, message, path and help.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct InaccessibleDiagnostic {
    pub key: Vec<String>,
    pub message: String,
    pub path: String,
    pub help: String,
}

/// Each distinct `(consumer handle, declaration handle)` usage and the S006s found on the way.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct SchemaUsages {
    pub usages: Vec<(usize, usize)>,
    pub diagnostics: Vec<InaccessibleDiagnostic>,
}

/// A path Python's visibility check rejects, with the scope it was checked against.
#[derive(Clone, Debug)]
pub struct RejectedScopePath {
    pub declared: DeclaredScope,
    pub path: String,
}

/// Where one merged macro dependency comes from.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DependencySource {
    /// The declaration's own dependency at this position.
    Own(usize),
    /// The declaration of the collected usage at this position.
    Usage(usize),
}
