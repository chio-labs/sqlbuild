//! Expand the `${...}` templates in one string exactly as the Python template resolver does.

use crate::templates::_helpers::evaluation::{evaluate, render_text};
use crate::templates::_helpers::expressions::parse_expression;
use crate::templates::_helpers::pattern::template_spans;
use crate::templates::models::{StringExpansion, TemplateFailure, TemplateOptions};
use crate::templates::types::TemplateHost;

/// Expand `text`: a whole-string template keeps its value, others are substituted as text.
pub fn expand_template_string<H: TemplateHost>(
    host: &H,
    text: &str,
    options: TemplateOptions,
) -> Result<StringExpansion<H::Value>, TemplateFailure> {
    let spans: Vec<(usize, usize)> = template_spans(text);
    if let [(start, end)] = spans.as_slice()
        && *start == 0
        && *end == text.len()
    {
        let expression = parse_expression(&text[2..text.len() - 1])?;
        return evaluate(host, &expression, options).map(StringExpansion::Value);
    }
    if spans.is_empty() {
        return Ok(StringExpansion::Unchanged);
    }
    let mut expanded = String::with_capacity(text.len());
    let mut copied = 0;
    for (start, end) in spans {
        expanded.push_str(&text[copied..start]);
        let expression = parse_expression(&text[start + 2..end - 1])?;
        let value = evaluate(host, &expression, options)?;
        expanded.push_str(&render_text(host, &value)?);
        copied = end;
    }
    expanded.push_str(&text[copied..]);
    Ok(StringExpansion::Text(expanded))
}
