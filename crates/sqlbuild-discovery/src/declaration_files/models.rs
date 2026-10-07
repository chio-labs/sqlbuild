//! Native results for enum, constant, schema, audit, hook, SQL function, seed and macro files.

use crate::declaration_files::types::Collection;
use crate::declarations::models::{DeclarationKind, DeclarationLayout};
use crate::models::{DiscoveredFile, DiscoveryFailure, LineColumnSpan, ProjectRoot, StageFailure};
use sqlbuild_core::text::models::PythonText;
use sqlbuild_sqltext::compiler::models::AuthoredValue;
use std::sync::{Arc, Mutex};

/// The header key sets Python owns and the Python semantics native parsing reproduces.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeclarationFileOptions {
    pub function_keys: Vec<String>,
    pub audit_keys: Vec<String>,
    pub hook_keys: Vec<String>,
    pub python: PythonText,
}

/// One collection Python's discovery reads, in its discovery order.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum CollectionKind {
    Enums,
    Constants,
    ModelSchemas,
    SqlFunctions,
    SqlHooks,
    Audits,
    Seeds,
    Macros,
}

impl CollectionKind {
    /// The stable name the facade requests a collection by.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Enums => "enum",
            Self::Constants => "constant",
            Self::ModelSchemas => "model_schema",
            Self::SqlFunctions => "sql_function",
            Self::SqlHooks => "sql_hook",
            Self::Audits => "audit",
            Self::Seeds => "seed",
            Self::Macros => "macro",
        }
    }

    /// The kind named `name`, if any.
    pub fn from_name(name: &str) -> Option<Self> {
        [
            Self::Enums,
            Self::Constants,
            Self::ModelSchemas,
            Self::SqlFunctions,
            Self::SqlHooks,
            Self::Audits,
            Self::Seeds,
            Self::Macros,
        ]
        .into_iter()
        .find(|kind| kind.as_str() == name)
    }
}

/// The scope facts Python attaches to a declaration file, with `/`-separated relative paths.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FileScope {
    /// Python's `DeclarationKind` value of the file's role.
    pub declaration_kind: &'static str,
    /// Python's `ScopeKind` value.
    pub scope_kind: &'static str,
    pub ownership_root: Option<String>,
    pub owning_path: Option<String>,
    pub declaration_root: Option<String>,
}

/// One discovered file with the scope facts of the role that holds it, if any.
#[derive(Clone, Debug, PartialEq)]
pub struct ScopedFile<T> {
    pub file: DiscoveredFile<T>,
    pub scope: Option<FileScope>,
}

/// Why a whole collection fails: an unreadable directory or an invalid declaration layout.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum CollectionFailure {
    Stage(StageFailure),
    Layout(DiscoveryFailure),
}

/// One public enum; member values are the authored values Python projects.
#[derive(Clone, Debug, PartialEq)]
pub struct EnumDeclaration {
    pub name: String,
    pub members: Vec<(String, AuthoredValue)>,
    /// `VARCHAR` or `INTEGER`.
    pub scalar_type: &'static str,
}

/// An enum file whose declarations all parsed.
#[derive(Clone, Debug, PartialEq)]
pub struct EnumFile {
    pub contents: String,
    pub declarations: Vec<EnumDeclaration>,
}

/// One public constant checked up to value normalisation, which Python performs.
#[derive(Clone, Debug, PartialEq)]
pub struct ConstantDeclaration {
    pub name: String,
    pub value: AuthoredValue,
    pub explicit_type: Option<String>,
    pub render_as: Option<String>,
}

/// A constant file: the declarations before the first native failure, then that failure.
#[derive(Clone, Debug, PartialEq)]
pub struct ConstantFile {
    pub contents: String,
    pub declarations: Vec<ConstantDeclaration>,
    pub failure: Option<DiscoveryFailure>,
}

/// One reusable model schema checked up to its columns, which Python parses.
#[derive(Clone, Debug, PartialEq)]
pub struct SchemaDeclaration {
    pub name: String,
    pub description: Option<String>,
    pub extends: Option<String>,
    pub columns: Option<AuthoredValue>,
    pub column_locations: Vec<(String, LineColumnSpan)>,
}

/// A schema file: the declarations before the first native failure, then that failure.
#[derive(Clone, Debug, PartialEq)]
pub struct SchemaFile {
    pub contents: String,
    pub declarations: Vec<SchemaDeclaration>,
    pub failure: Option<DiscoveryFailure>,
}

/// One `AUDIT(...)` block; values mirror Python's `DiscoveredAuditBlock`.
#[derive(Clone, Debug, PartialEq)]
pub struct AuditBlock {
    pub audit_index: usize,
    pub header_values: Vec<(String, AuthoredValue)>,
    pub sql_body: String,
    pub name: Option<String>,
    /// `violations` or `measurement`.
    pub evaluation_mode: &'static str,
    pub measure_sql: Option<String>,
    pub evidence_sql: Option<String>,
}

/// An audit file whose blocks all parsed.
#[derive(Clone, Debug, PartialEq)]
pub struct AuditFile {
    pub contents: String,
    pub blocks: Vec<AuditBlock>,
}

/// A named SQL hook file; values mirror Python's `DiscoveredSqlHookFile`.
#[derive(Clone, Debug, PartialEq)]
pub struct HookFile {
    pub contents: String,
    pub header_values: Vec<(String, AuthoredValue)>,
    pub sql_body: String,
    pub name: String,
    pub description: Option<String>,
}

/// A SQL function file; values mirror Python's `DiscoveredSqlFunctionFile`.
#[derive(Clone, Debug, PartialEq)]
pub struct FunctionFile {
    pub contents: String,
    pub header_values: Vec<(String, AuthoredValue)>,
    pub body_sql: String,
}

/// A macro file's text; Python analyses and imports it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MacroFile {
    pub contents: String,
}

/// A seed file; Python reads seeds when it loads them.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SeedFile;

/// One discovered collection, retained for later native stages.
#[derive(Clone, Debug, PartialEq)]
pub enum DeclarationCollection {
    Enums(Collection<EnumFile>),
    Constants(Collection<ConstantFile>),
    ModelSchemas(Collection<SchemaFile>),
    SqlFunctions(Collection<FunctionFile>),
    SqlHooks(Collection<HookFile>),
    Audits(Collection<AuditFile>),
    Seeds(Collection<SeedFile>),
    Macros(Collection<MacroFile>),
}

/// One in-memory parse of `contents` as a `kind` file named `file_path`.
#[derive(Clone, Debug, PartialEq)]
pub enum ParsedDeclarationText {
    Enum(EnumFile),
    Constant(ConstantFile),
    ModelSchema(SchemaFile),
    SqlFunction(FunctionFile),
    SqlHook(HookFile),
    Audit(AuditFile),
}

/// One collection a discovery pass asks for; macro, enum and constant layouts may be isolated.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct CollectionRequest {
    pub kind: CollectionKind,
    /// Read the layout of this declaration kind alone, as tolerant discovery does.
    pub isolate_kind: bool,
}

/// One collection a discovery pass read, kept for later native stages.
#[derive(Clone, Debug)]
pub struct RetainedCollection {
    pub request: CollectionRequest,
    pub collection: Arc<DeclarationCollection>,
}

/// The declaration layout one discovery pass read for a kind, or for every kind with `None`.
#[derive(Clone, Debug)]
pub struct RetainedLayout {
    pub kind: Option<DeclarationKind>,
    pub layout: Arc<Result<DeclarationLayout, StageFailure>>,
}

/// The declaration collections one discovery pass read, retained for later native stages.
#[derive(Debug)]
pub struct DiscoverySession {
    pub root: ProjectRoot,
    pub options: DeclarationFileOptions,
    pub collections: Mutex<Vec<RetainedCollection>>,
    /// The layouts the collections were listed from, walked once per pass.
    pub layouts: Mutex<Vec<RetainedLayout>>,
}

impl DiscoverySession {
    /// A session of `root` that has read nothing yet.
    pub fn new(root: ProjectRoot, options: DeclarationFileOptions) -> Self {
        Self {
            root,
            options,
            collections: Mutex::new(Vec::new()),
            layouts: Mutex::new(Vec::new()),
        }
    }
}
