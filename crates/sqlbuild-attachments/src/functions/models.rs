//! Function header values as Python holds them and what Python's attachment parses from them.

/// One authored header value: text, a mapping, a list or tuple, or anything else.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum HeaderValue {
    Text(String),
    Map(Vec<(HeaderValue, HeaderValue)>),
    Sequence(Vec<HeaderValue>),
    Other,
}

/// Which function file kind's header rules apply.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FunctionLanguage {
    Sql,
    Python,
}

/// One argument or return column: the authored name, the stripped name and the stripped type.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NamedType {
    /// Python's error messages quote the name as authored.
    pub raw_name: String,
    pub name: String,
    pub type_text: String,
}

/// A scalar return type or table function columns, with types before template expansion.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum FunctionReturns {
    Type(String),
    Table(Vec<NamedType>),
}

/// Stripped header values; argument, return and column types are still unexpanded templates.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FunctionHeader {
    pub arguments: Vec<NamedType>,
    pub returns: FunctionReturns,
    pub tags: Vec<String>,
    pub description: Option<String>,
    /// Python functions only: `runtime_version`, `entry_point` and `packages`.
    pub runtime_version: Option<String>,
    pub entry_point: Option<String>,
    pub packages: Vec<String>,
}

/// The project and target namespace a function resolves against, already expanded.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NamespaceInputs {
    /// The function header's own `database` and `schema`, when they are strings.
    pub header_database: Option<String>,
    pub header_schema: Option<String>,
    pub default_database: Option<String>,
    pub default_schema: Option<String>,
    pub target_database: Option<String>,
    pub target_schema: Option<String>,
    /// Python functions without their own namespace inherit the project defaults.
    pub language: FunctionLanguage,
    pub inherit_default_namespace: bool,
}

/// Python's resolved physical, logical and fingerprint namespace of one function.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct FunctionNamespace {
    pub database: Option<String>,
    pub schema: Option<String>,
    pub logical_database: Option<String>,
    pub logical_schema: Option<String>,
    pub fingerprint_database: Option<String>,
    pub fingerprint_schema: Option<String>,
    pub fingerprint_logical_database: Option<String>,
    pub fingerprint_logical_schema: Option<String>,
}
