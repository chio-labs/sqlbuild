//! Substitute each `${...}` template in a string by its rendered value.

use crate::templates::_helpers::evaluation::evaluate;
use crate::templates::_helpers::expressions::parse_expression;
use crate::templates::models::{TemplateFailure, TemplateOptions};
use crate::templates::types::TemplateHost;

/// `text` with every template at `spans` replaced by its value rendered as text.
pub(crate) fn substituted<H: TemplateHost>(
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
