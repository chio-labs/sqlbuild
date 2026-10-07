//! What template evaluation reads from its caller.

use crate::templates::models::{ContextValue, Scalar, TemplateFailure};

/// The variables, environment and context one template expansion reads, owned by the caller.
pub trait TemplateHost {
    /// One evaluated value; Python objects in the bindings.
    type Value: Clone;

    /// Return a project variable, or `None` when it is not defined.
    fn variable(&self, name: &str) -> Result<Option<Self::Value>, TemplateFailure>;
    /// Record an environment read and return the variable, or `None` when it is not set.
    fn environment(&self, name: &str) -> Result<Option<Self::Value>, TemplateFailure>;
    /// Record a context read and return the context value.
    fn context(&self, name: &str) -> Result<ContextValue<Self::Value>, TemplateFailure>;
    /// Return a text value.
    fn text(&self, text: &str) -> Result<Self::Value, TemplateFailure>;
    /// Return a boolean value.
    fn boolean(&self, flag: bool) -> Result<Self::Value, TemplateFailure>;
    /// Return the null value.
    fn null(&self) -> Self::Value;
    /// Return the scalar `value` is, or `None` when only Python can render or compare it.
    fn scalar(&self, value: &Self::Value) -> Option<Scalar>;
}
