//! Expand every `${...}` template in one string as text.

use crate::templates::_helpers::pattern::template_spans;
use crate::templates::_helpers::substitution::substituted;
use crate::templates::models::{TemplateFailure, TemplateOptions};
use crate::templates::types::TemplateHost;

/// Substitute every template in `text` as text, as `expand_template_string` does in Python.
pub fn expand_template_text<H: TemplateHost>(
    host: &H,
    text: &str,
    options: TemplateOptions,
) -> Result<String, TemplateFailure> {
    substituted(host, text, &template_spans(text), options)
}
