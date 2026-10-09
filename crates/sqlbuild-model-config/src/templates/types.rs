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
    /// Return `value` as the resolver compares it: `None`, a `bool` or its `str()`.
    fn scalar(&self, value: &Self::Value) -> Result<Scalar, TemplateFailure>;
    /// Render `value` inside a larger string as `render_project_var_text` does for `label`.
    fn render(&self, value: &Self::Value, label: &str) -> Result<String, TemplateFailure>;
    /// The context label error messages start with.
    fn label(&self) -> &str;
}
