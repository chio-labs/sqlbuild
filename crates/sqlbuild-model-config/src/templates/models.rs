//! Template expressions, scalar values and outcomes.

/// A parsed `${...}` expression.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Expression {
    Text(String),
    Reference(String),
    Function {
        name: String,
        arguments: Vec<Expression>,
    },
}

/// A value whose text Python's `str()` produces without calling user code.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Scalar {
    Null,
    Bool(bool),
    /// An exact `str` or the decimal digits of an exact `int`.
    Text(String),
}

/// One context lookup.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ContextValue<V> {
    Unknown,
    /// The key is known but has no value yet.
    Unavailable,
    Value(V),
}

/// Why native expansion stops; Python then expands the value itself.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TemplateFailure {
    /// A missing variable, environment variable or context value, which `coalesce` skips.
    Missing,
    /// Python raises another error for this template.
    Invalid,
    /// Python expands this template with rules the native expansion does not reproduce.
    Unsupported,
}

/// How evaluation treats `CTX:` references, mirroring the Python resolver's flags.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TemplateOptions {
    pub allow_context: bool,
    pub preserve_context_tokens: bool,
    pub preserve_unknown_context: bool,
}

/// One string's expansion.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum StringExpansion<V> {
    /// The string holds no complete template and stays the same object.
    Unchanged,
    /// The whole string was one template, which evaluated to this value.
    Value(V),
    /// The templates inside the string were substituted.
    Text(String),
}
