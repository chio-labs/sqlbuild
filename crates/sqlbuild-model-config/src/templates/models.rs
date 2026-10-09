//! Template expressions, scalar values and outcomes.

use crate::templates::errors::TemplateError;

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

/// A value as the Python resolver compares and tests it: `None`, a `bool` or its `str()`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Scalar {
    Null,
    Bool(bool),
    /// The value's `str()`.
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

/// Why native expansion stops.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum TemplateFailure {
    /// A missing variable, environment variable or context value, which `coalesce` skips.
    Missing(TemplateError),
    /// Another error Python raises for this template.
    Invalid(TemplateError),
    /// The host raised an error of its own, which it holds and reports.
    Host,
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
