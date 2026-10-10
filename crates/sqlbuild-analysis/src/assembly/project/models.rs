//! The project assembly request Python builds from its compile inputs, and the facts it returns.

use sqlbuild_model_config::templates::models::Scalar;

use crate::assembly::analysis_session::types::Pairs;
use crate::assembly::project::types::ObjectKey;

/// One SQL reference a resource makes: Python's `CompileSqlReference`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Reference {
    /// The `SqlReferenceKind` value.
    pub kind: String,
    pub name: String,
    pub package: Option<String>,
}

/// One project variable, as a scalar Python renders with `str()`, or a value only Python renders.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Variable {
    Scalar(Scalar),
    Unsupported,
}

/// One environment or context lookup a template made, which Python records for compile reuse.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum InputRead {
    Environment(String),
    Context(String),
}

/// The selected target's namespace settings.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct TargetNamespace {
    pub database: Option<String>,
    pub schema: Option<String>,
    pub loader_schema: Option<String>,
}

/// The project defaults a seed's logical namespace reads.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SeedDefaults {
    pub database: Option<String>,
    pub schema: Option<String>,
    pub seed_database: Option<String>,
    pub seed_schema: Option<String>,
}

/// One model or hook SQL string Python's syntax validation checks, with its placeholders.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SyntaxCheck {
    pub sql: String,
    pub placeholders: Pairs,
}

/// Which Polyglot entry point Python's validation calls.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SyntaxMode {
    /// `validate`, for model queries and hooks.
    Validate,
    /// `parse_one`, for function bodies and source expressions.
    Parse,
}

/// Where Python's syntax validation raises instead of reporting a message.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SyntaxFailure {
    /// The analysis normalization's `ValueError` message.
    Normalization(String),
    /// Polyglot does not know the dialect name.
    UnknownDialect(String),
}

/// One model's identity, graph facts, references and the SQL strings its assembly validates.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModelFacts {
    /// The model's name: its file stem, the name of its `("model", name)` key.
    pub name: String,
    /// `str(model_file.relative_path.parent)`, the folder project selectors match.
    pub directory: String,
    /// `config.values["tags"]` items as `str()` where a list or tuple, else empty.
    pub tags: Vec<String>,
    pub references: Vec<Reference>,
    pub syntax_checks: Vec<SyntaxCheck>,
}

/// One source's name, whether a loader manages it, and its authored namespace.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SourceFacts {
    pub name: String,
    pub managed: bool,
    pub database: Option<String>,
    pub schema: Option<String>,
}

/// One seed's name, tags and authored namespace.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SeedFacts {
    pub name: String,
    /// `schema_entry.tags`.
    pub tags: Vec<String>,
    pub database: Option<String>,
    pub schema: Option<String>,
}

/// One SQL function's key, tags and references.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FunctionFacts {
    /// `function_node_type(return_columns)`: `udf` or `table_fn`, its key's resource type.
    pub kind: String,
    pub name: String,
    pub tags: Vec<String>,
    pub references: Vec<Reference>,
}

/// One audit's references and the resource it is attached to.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuditFacts {
    pub references: Vec<Reference>,
    /// The attached resource's `(resource type, name)`.
    pub attached: Option<(String, String)>,
}

/// Everything one project's resource assembly reads.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProjectRequest {
    /// The analysis dialect syntax validation parses with, `generic` when the adapter names none.
    pub dialect: String,
    pub target: Option<TargetNamespace>,
    pub defaults: SeedDefaults,
    pub variables: Vec<(String, Variable)>,
    /// Python's `os.environ.get` of every name an `ENV:` template in the request names.
    pub environment: Vec<(String, Option<String>)>,
    pub models: Vec<ModelFacts>,
    pub sources: Vec<SourceFacts>,
    pub seeds: Vec<SeedFacts>,
    pub functions: Vec<FunctionFacts>,
    pub audits: Vec<AuditFacts>,
}

/// A relation's physical and logical namespace.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Namespace {
    pub database: Option<String>,
    pub schema: Option<String>,
    pub logical_database: Option<String>,
    pub logical_schema: Option<String>,
}

/// The facts Python's resource assembly derives, in input order.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ProjectResources {
    pub model_deps: Vec<Vec<ObjectKey>>,
    /// Whether every SQL string a model's assembly validates parses; where one does not,
    /// Python's validation reports it with its message and location.
    pub model_syntax_valid: Vec<bool>,
    /// A managed source's `(database, schema)`; None where the entry stays as authored.
    pub sources: Vec<Option<(Option<String>, Option<String>)>>,
    pub seeds: Vec<Namespace>,
    pub function_deps: Vec<Vec<ObjectKey>>,
    pub audit_deps: Vec<Vec<ObjectKey>>,
    pub reads: Vec<InputRead>,
}
