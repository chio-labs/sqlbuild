//! Shared compiler identities, diagnostics and typed SQL values mirrored from Python.

use std::cmp::Ordering;
use std::fmt;

/// Resource type of a compiled object, Python's `CompiledResourceType`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum CompiledResourceType {
    Model,
    Source,
    Seed,
    Udf,
    TableFn,
    DbtRef,
    Audit,
    SqlTest,
    SqlScenario,
}

impl CompiledResourceType {
    /// The Python enum value, which is also the serialized form.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Model => "model",
            Self::Source => "source",
            Self::Seed => "seed",
            Self::Udf => "udf",
            Self::TableFn => "table_fn",
            Self::DbtRef => "dbt_ref",
            Self::Audit => "audit",
            Self::SqlTest => "sql_test",
            Self::SqlScenario => "sql_scenario",
        }
    }
}

/// Logical identity of one compiled resource or external dependency, Python's `CompiledObjectKey`.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct CompiledObjectKey {
    pub resource_type: CompiledResourceType,
    pub name: String,
}

/// Kind of an authored resource in the scope index, Python's `ResourceKind`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ResourceKind {
    Model,
    Test,
    Scenario,
    Function,
    Source,
    Seed,
}

impl ResourceKind {
    /// The Python enum value, which is also the serialized form.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Model => "model",
            Self::Test => "test",
            Self::Scenario => "scenario",
            Self::Function => "function",
            Self::Source => "source",
            Self::Seed => "seed",
        }
    }
}

/// Independent declaration namespace, Python's `DeclarationKind`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum DeclarationKind {
    Macro,
    Enum,
    Constant,
    Audit,
    SingularAudit,
    Schema,
    SqlHook,
    PythonHook,
}

impl DeclarationKind {
    /// The Python enum value, which is also the serialized form.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Macro => "macro",
            Self::Enum => "enum",
            Self::Constant => "constant",
            Self::Audit => "audit",
            Self::SingularAudit => "singular_audit",
            Self::Schema => "schema",
            Self::SqlHook => "sql_hook",
            Self::PythonHook => "python_hook",
        }
    }
}

/// Kind-qualified identity of one authored resource, displayed as `kind:name`.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct ResourceIdentity {
    pub kind: ResourceKind,
    pub name: String,
}

/// Declaration identity, displayed as `kind:name` or `kind:owner_kind:owner_name.name`.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct DeclarationIdentity {
    pub kind: DeclarationKind,
    pub name: String,
    pub owner: Option<ResourceIdentity>,
}

/// Orders by kind value then name, as Python's `order=True` dataclass compares its fields.
impl Ord for ResourceIdentity {
    fn cmp(&self, other: &Self) -> Ordering {
        (self.kind.as_str(), self.name.as_str()).cmp(&(other.kind.as_str(), other.name.as_str()))
    }
}

impl PartialOrd for ResourceIdentity {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

/// Orders by kind value, name, then owner; a public declaration sorts before a private twin.
impl Ord for DeclarationIdentity {
    fn cmp(&self, other: &Self) -> Ordering {
        (self.kind.as_str(), self.name.as_str(), &self.owner).cmp(&(
            other.kind.as_str(),
            other.name.as_str(),
            &other.owner,
        ))
    }
}

impl PartialOrd for DeclarationIdentity {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

/// The text of Python's `format_identity`.
impl fmt::Display for ResourceIdentity {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}:{}", self.kind.as_str(), self.name)
    }
}

/// The text of Python's `format_identity`.
impl fmt::Display for DeclarationIdentity {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match &self.owner {
            None => write!(formatter, "{}:{}", self.kind.as_str(), self.name),
            Some(owner) => write!(
                formatter,
                "{}:{}:{}.{}",
                self.kind.as_str(),
                owner.kind.as_str(),
                owner.name,
                self.name
            ),
        }
    }
}

/// Phase that produced a diagnostic, Python's `DiagnosticPhase`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum DiagnosticPhase {
    Compile,
    Contract,
    Rule,
    Plan,
    Build,
    Audit,
    Test,
    Connection,
}

impl DiagnosticPhase {
    /// The Python enum value, which is also the serialized form.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Compile => "compile",
            Self::Contract => "contract",
            Self::Rule => "rule",
            Self::Plan => "plan",
            Self::Build => "build",
            Self::Audit => "audit",
            Self::Test => "test",
            Self::Connection => "connection",
        }
    }
}

/// Severity of a diagnostic, Python's `DiagnosticSeverity`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum DiagnosticSeverity {
    Error,
    Warning,
    Info,
}

impl DiagnosticSeverity {
    /// The Python enum value, which is also the serialized form.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Error => "error",
            Self::Warning => "warning",
            Self::Info => "info",
        }
    }
}

/// An authored location with 1-based lines and code-point columns, Python's `SourceLocation`.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct SourceLocation {
    pub path: String,
    pub line: usize,
    pub column: usize,
    pub end_line: Option<usize>,
    pub end_column: Option<usize>,
}

/// A secondary location that adds context to a diagnostic, Python's `RelatedLocation`.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct RelatedLocation {
    pub label: String,
    pub location: SourceLocation,
    pub message: Option<String>,
}

/// Serial emission position: resource compile order, then stage, then sequence within it.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct DiagnosticOrderKey {
    pub resource_order: u32,
    pub stage: u32,
    pub sequence: u32,
}

/// One compile-time diagnostic, Python's `CompilerDiagnostic` plus its serial order key.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct Diagnostic {
    pub phase: DiagnosticPhase,
    pub severity: DiagnosticSeverity,
    pub code: String,
    pub message: String,
    pub resource_type: Option<CompiledResourceType>,
    pub resource_name: Option<String>,
    pub column_name: Option<String>,
    pub location: Option<SourceLocation>,
    pub related_locations: Vec<RelatedLocation>,
    pub help: Option<String>,
    pub notes: Vec<String>,
    pub affected_rules: Vec<String>,
    pub order_key: DiagnosticOrderKey,
}

impl Diagnostic {
    /// Whether this diagnostic fails the command.
    pub fn is_error(&self) -> bool {
        self.severity == DiagnosticSeverity::Error
    }
}

/// Closed logical kinds of typed SQL values, Python's `SqlValueKind`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum SqlValueKind {
    String,
    Integer,
    Boolean,
    Float,
    Decimal,
    Null,
    List,
    Set,
    Object,
}

impl SqlValueKind {
    /// The Python enum value, which is also the serialized form.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::String => "string",
            Self::Integer => "integer",
            Self::Boolean => "boolean",
            Self::Float => "float",
            Self::Decimal => "decimal",
            Self::Null => "null",
            Self::List => "list",
            Self::Set => "set",
            Self::Object => "object",
        }
    }
}

/// Logical type of a typed SQL value; collections carry their element type.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct SqlLogicalType {
    pub kind: SqlValueKind,
    pub element_type: Option<Box<SqlLogicalType>>,
}

impl SqlLogicalType {
    /// Python's `display_name`, such as `list<integer>`.
    pub fn display_name(&self) -> String {
        match &self.element_type {
            None => self.kind.as_str().to_owned(),
            Some(element) => format!("{}<{}>", self.kind.as_str(), element.display_name()),
        }
    }
}

/// One validated, canonical typed SQL value, Python's normalized `SqlValue` (see crates/README.md).
#[derive(Clone, Debug, PartialEq)]
pub enum SqlValue {
    Null,
    Boolean(bool),
    Integer(i64),
    Float(f64),
    Decimal(String),
    String(String),
    List {
        element_type: SqlLogicalType,
        values: Vec<SqlValue>,
    },
    Set {
        element_type: SqlLogicalType,
        values: Vec<SqlValue>,
    },
    Object(Vec<(String, SqlValue)>),
}

impl SqlValue {
    /// The logical type of this value.
    pub fn logical_type(&self) -> SqlLogicalType {
        let (kind, element_type) = match self {
            Self::Null => (SqlValueKind::Null, None),
            Self::Boolean(_) => (SqlValueKind::Boolean, None),
            Self::Integer(_) => (SqlValueKind::Integer, None),
            Self::Float(_) => (SqlValueKind::Float, None),
            Self::Decimal(_) => (SqlValueKind::Decimal, None),
            Self::String(_) => (SqlValueKind::String, None),
            Self::List { element_type, .. } => (SqlValueKind::List, Some(element_type)),
            Self::Set { element_type, .. } => (SqlValueKind::Set, Some(element_type)),
            Self::Object(_) => (SqlValueKind::Object, None),
        };
        SqlLogicalType {
            kind,
            element_type: element_type.map(|element| Box::new(element.clone())),
        }
    }
}
