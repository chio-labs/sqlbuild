//! Plain-data facts a refactoring reads, and the plan it produces, as Python's models hold them.
//!
//! Every offset counts code points, as Python string offsets do.

use serde::{Deserialize, Serialize};

/// One supported refactoring.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RefactorOperation {
    RenameModel,
    MoveModel,
    RenameColumn,
}

/// What one text edit changes, for output grouping.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EditKind {
    Reference,
    Fixture,
    Header,
    Column,
    Migration,
}

impl EditKind {
    /// The kind's value in output, as Python's `EditKind` enum spells it.
    pub fn value(self) -> &'static str {
        match self {
            Self::Reference => "reference",
            Self::Fixture => "fixture",
            Self::Header => "header",
            Self::Column => "column",
            Self::Migration => "migration",
        }
    }
}

/// What an authored SQL file declares.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SqlFileRole {
    Model,
    Test,
    Scenario,
    Audit,
    Hook,
    Function,
    Schema,
    Yaml,
}

/// One requested rename or move.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct RefactorRequest {
    pub operation: RefactorOperation,
    pub model_name: String,
    pub new_name: String,
    #[serde(default)]
    pub column_name: Option<String>,
    #[serde(default)]
    pub destination: Option<String>,
    #[serde(default)]
    pub cascade: bool,
}

/// One replacement in an authored file, in offsets of the file before any edit.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct TextEdit {
    pub start: usize,
    pub end: usize,
    pub replacement: String,
    pub kind: EditKind,
    pub line: usize,
    pub column: usize,
    pub before: String,
    pub after: String,
}

/// Every edit to one file, and where the file lives afterwards.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct FileChange {
    pub path: String,
    pub original_path: String,
    pub edits: Vec<TextEdit>,
}

impl FileChange {
    /// Whether the change moves the file.
    pub fn moved(&self) -> bool {
        self.path != self.original_path
    }
}

/// A location a refactoring cannot rewrite safely.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct ManualLocation {
    pub path: String,
    pub line: Option<usize>,
    pub column: Option<usize>,
    pub reason: String,
}

/// A `migrate_from` declaration the refactoring adds to keep history.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct MigrationDeclaration {
    pub model_name: String,
    pub declaration: String,
    pub reason: String,
}

/// Every edit, manual location, and migration of one refactoring.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct RefactorPlan {
    pub request: RefactorRequest,
    pub changes: Vec<FileChange>,
    pub manual: Vec<ManualLocation>,
    pub blocking: Vec<ManualLocation>,
    pub migrations: Vec<MigrationDeclaration>,
    pub renamed_columns: Vec<(String, String, String)>,
    pub help: Option<String>,
}

impl RefactorPlan {
    /// The number of text edits the plan writes, over every changed file.
    pub fn edit_count(&self) -> usize {
        self.changes.iter().map(|change| change.edits.len()).sum()
    }
}

/// One rendered region of an expansion pass, pairing its source range with its output range.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct ExpansionSpan {
    pub source_start: usize,
    pub source_end: usize,
    pub output_start: usize,
    pub output_end: usize,
}

/// Authored-to-expanded SQL evidence of one model file.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct ExpansionFacts {
    pub expanded_sql: String,
    pub passes: Vec<Vec<ExpansionSpan>>,
}

/// The relation a model builds.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct DestinationFacts {
    pub database: Option<String>,
    pub schema: Option<String>,
    pub name: String,
}

/// Where a column is declared.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct LocationFacts {
    pub path: String,
    pub line: Option<usize>,
    pub column: Option<usize>,
}

/// One declared column of a model's schema entry.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct SchemaColumnFacts {
    pub name: String,
    /// Whether the column declares a `migrate_from`.
    pub migrate_from: bool,
    pub location: Option<LocationFacts>,
}

/// One dependency of a model.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct DependencyFacts {
    pub resource_type: String,
    pub name: String,
}

/// Every compiler fact of one model a refactoring reads.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct ModelFacts {
    pub name: String,
    /// The project-relative POSIX path of the model file.
    pub path: String,
    pub deps: Vec<DependencyFacts>,
    pub query_sql: String,
    pub authored_query_sql: String,
    /// The authored `materialized` string config, as `get_config_str` returns it.
    pub materialized: Option<String>,
    /// Whether `migrate_from` is a key of the model config.
    pub declares_migrate_from: bool,
    /// Whether the model config's `migrate_from` value is not `None`.
    pub migrate_from_set: bool,
    pub destination: DestinationFacts,
    pub inferred_columns: Vec<String>,
    /// The columns of the model's schema entry, or `None` without a schema entry.
    pub schema_columns: Option<Vec<SchemaColumnFacts>>,
    /// The expansion of the model's file, if the compiler recorded one.
    pub expansion: Option<ExpansionFacts>,
}

/// The output columns of one source or seed.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct ResourceColumnsFacts {
    pub name: String,
    pub columns: Vec<String>,
}

/// One discovered file and its authored contents.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct DiscoveredFile {
    pub path: String,
    pub contents: String,
}

/// One discovered non-model SQL file with the SQL bodies discovery found in it, in file order.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct AuthoredFile {
    pub role: SqlFileRole,
    pub path: String,
    pub contents: String,
    pub texts: Vec<String>,
}

/// Declaration files a model move takes along, and what blocks the move.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct DeclarationMoves {
    pub moves: Vec<(String, String)>,
    pub blocking: Vec<ManualLocation>,
}

/// Every compiler fact of one project a refactoring plan reads.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct RefactorFacts {
    /// The resolved project directory.
    pub project_dir: String,
    /// The SQL analysis dialect, or `generic`.
    pub dialect: String,
    /// The `(major, minor)` Python version whose string semantics apply.
    pub python_version: (u8, u8),
    /// Python's `unicodedata.unidata_version`.
    pub unicode_version: String,
    pub models: Vec<ModelFacts>,
    pub sources: Vec<ResourceColumnsFacts>,
    pub seeds: Vec<ResourceColumnsFacts>,
    /// Discovered model files, in discovery order.
    pub model_files: Vec<DiscoveredFile>,
    /// Discovered test, scenario, audit, hook, function and schema files, in Python's order.
    pub authored_files: Vec<AuthoredFile>,
    /// Discovered source and seed YAML declaration files, in discovery order.
    pub yaml_files: Vec<DiscoveredFile>,
    /// Python strings naming the renamed model or column, found by the Python host.
    pub python_locations: Vec<ManualLocation>,
    /// Declaration moves of a model move across folders, worked out by the Python host.
    #[serde(default)]
    pub declaration_moves: Option<DeclarationMoves>,
}

/// Which Python exception an expected refactoring failure becomes.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum RefactorErrorKind {
    /// `RefactorInputError`: the request cannot be planned.
    Input,
    /// `RefactorEditError`: two planned edits overlap.
    Edit,
    /// `RefactorWriteError`: project files changed while the refactoring ran.
    Write,
    /// Native code cannot reproduce this plan exactly; the Python planner must run instead.
    Deferred,
    /// A `ValueError` the Python planner does not handle, such as a header the tokenizer rejects.
    Value,
}

/// An expected refactoring failure with Python's code, message and help.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct RefactorError {
    pub kind: RefactorErrorKind,
    pub code: String,
    pub message: String,
    pub help: Option<String>,
}

impl RefactorError {
    /// A `RefactorInputError` with an explicit code.
    pub fn input(code: &str, message: impl Into<String>, help: Option<&str>) -> Self {
        Self {
            kind: RefactorErrorKind::Input,
            code: code.to_owned(),
            message: message.into(),
            help: help.map(str::to_owned),
        }
    }

    /// An unhandled `ValueError` with Python's message.
    pub fn value(message: String) -> Self {
        Self {
            kind: RefactorErrorKind::Value,
            code: String::new(),
            message,
            help: None,
        }
    }

    /// A deferral to the Python planner, with the reason native code stopped.
    pub fn deferred(message: impl Into<String>) -> Self {
        Self {
            kind: RefactorErrorKind::Deferred,
            code: String::new(),
            message: message.into(),
            help: None,
        }
    }
}
