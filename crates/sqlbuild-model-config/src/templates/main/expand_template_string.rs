//! Expand the `${...}` templates in one string exactly as the Python template resolver does.

use crate::templates::_helpers::evaluation::evaluate;
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
    substituted(host, text, &spans, options).map(StringExpansion::Text)
}

/// Substitute every template in `text` as text, as `expand_template_string` does in Python.
pub fn expand_template_text<H: TemplateHost>(
    host: &H,
    text: &str,
    options: TemplateOptions,
) -> Result<String, TemplateFailure> {
    substituted(host, text, &template_spans(text), options)
}

fn substituted<H: TemplateHost>(
    host: &H,
    text: &str,
    spans: &[(usize, usize)],
    options: TemplateOptions,
) -> Result<String, TemplateFailure> {
    let mut expanded = String::with_capacity(text.len());
    let mut copied = 0;
    for &(start, end) in spans {
        expanded.push_str(&text[copied..start]);
        let body = &text[start + 2..end - 1];
        let expression = parse_expression(body)?;
        let value = evaluate(host, &expression, options)?;
        let label = format!("{} variable '{body}'", host.label());
        expanded.push_str(&host.render(&value, &label)?);
        copied = end;
    }
    expanded.push_str(&text[copied..]);
    Ok(expanded)
}
