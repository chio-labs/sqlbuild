//! Call sites, analysis SQL and authored offsets, as `sql_sites.py` finds them.

use std::collections::BTreeSet;

use sqlbuild_core::text::main::is_python_space::is_python_space;

use crate::refactoring::_helpers::scanning::chars::{chars, rfind, slice, starts_with};
use crate::refactoring::_helpers::scanning::interpolation::interpolation_sites;
use crate::refactoring::_helpers::scanning::scan_context::ScanContext;
use crate::refactoring::constants::{GENERIC_PLACEHOLDER_KIND, PLACEHOLDER_PAD, REF_FUNCTION};
use crate::refactoring::models::{ExpansionSpan, ModelFacts};

/// One `__ref`, `__source`, or `__seed` call written in authored SQL.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct ResourceSite {
    pub(crate) kind: String,
    pub(crate) name: String,
    pub(crate) start: usize,
    pub(crate) end: usize,
    pub(crate) name_start: usize,
    pub(crate) name_end: usize,
}

/// SQL whose interpolation sites were replaced by same-length identifiers.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(crate) struct AnalysisSql {
    pub(crate) sql: String,
    /// Each resource call `(kind, name)` with its placeholders, in first appearance order.
    pub(crate) tables: Vec<((String, String), BTreeSet<String>)>,
}

impl AnalysisSql {
    /// The placeholders of one resource, or none.
    pub(crate) fn placeholders(&self, kind: &str, name: &str) -> BTreeSet<String> {
        self.tables
            .iter()
            .find(|((item_kind, item_name), _)| item_kind == kind && item_name == name)
            .map(|(_, placeholders)| placeholders.clone())
            .unwrap_or_default()
    }
}

/// A model's compiled query and how it maps onto the authored file.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct ModelBody {
    pub(crate) body_start: usize,
    pub(crate) compiled_sql: String,
    pub(crate) passes: Vec<Vec<ExpansionSpan>>,
}

/// `RESOURCE_CALL_PATTERN` on a site's text: `(kind, name, name_start, name_end)`.
fn resource_call(text: &[char]) -> Option<(String, String, usize, usize)> {
    if !starts_with(text, 0, "__") {
        return None;
    }
    let kind = ["ref", "source", "seed"]
        .into_iter()
        .find(|kind| starts_with(text, 2, kind))?;
    let mut index = 2 + kind.len();
    index = skip_space(text, index);
    if text.get(index) != Some(&'(') {
        return None;
    }
    index = skip_space(text, index + 1);
    let quote = *text
        .get(index)
        .filter(|character| matches!(character, '\'' | '"'))?;
    let name_start = index + 1;
    let mut name_end = name_start;
    while text
        .get(name_end)
        .is_some_and(|character| !matches!(character, '\'' | '"'))
    {
        name_end += 1;
    }
    if name_end == name_start || text.get(name_end) != Some(&quote) {
        return None;
    }
    index = skip_space(text, name_end + 1);
    if text.get(index) != Some(&')') {
        return None;
    }
    let rest = &text[index + 1..];
    if !(rest.is_empty() || rest == ['\n']) {
        return None;
    }
    Some((
        kind.to_owned(),
        slice(text, name_start, name_end),
        name_start,
        name_end,
    ))
}

fn skip_space(text: &[char], mut index: usize) -> usize {
    while text.get(index).copied().is_some_and(is_python_space) {
        index += 1;
    }
    index
}

/// Resource calls outside comments and strings, with their name spans.
pub(crate) fn resource_sites(text: &[char], context: &ScanContext) -> Vec<ResourceSite> {
    interpolation_sites(text, context.backtick_identifiers, context.python)
        .into_iter()
        .filter_map(|site| {
            let (kind, name, name_start, name_end) = resource_call(&chars(&site.text))?;
            Some(ResourceSite {
                kind,
                name,
                start: site.start,
                end: site.end,
                name_start: site.start + name_start,
                name_end: site.start + name_end,
            })
        })
        .collect()
}

/// `EMBEDDED_REF_PATTERN` name spans of `__ref` calls inside a quoted string's raw text.
pub(crate) fn embedded_ref_spans(text: &[char], name: &str) -> Vec<(usize, usize)> {
    let mut spans: Vec<(usize, usize)> = Vec::new();
    let mut index = 0;
    while index < text.len() {
        match embedded_ref_at(text, index) {
            Some((name_start, name_end, end)) => {
                if slice(text, name_start, name_end) == name {
                    spans.push((name_start, name_end));
                }
                index = end;
            }
            None => index += 1,
        }
    }
    spans
}

/// `__ref\s*\(\s*\\?['"](?P<name>[^'"\\]+)\\?['"]\s*\)` at `index`: name span and match end.
fn embedded_ref_at(text: &[char], index: usize) -> Option<(usize, usize, usize)> {
    if !starts_with(text, index, REF_FUNCTION) {
        return None;
    }
    let mut position = skip_space(text, index + REF_FUNCTION.len());
    if text.get(position) != Some(&'(') {
        return None;
    }
    position = skip_space(text, position + 1);
    if text.get(position) == Some(&'\\') {
        position += 1;
    }
    if !text
        .get(position)
        .is_some_and(|character| matches!(character, '\'' | '"'))
    {
        return None;
    }
    let name_start = position + 1;
    let mut name_end = name_start;
    while text
        .get(name_end)
        .is_some_and(|character| !matches!(character, '\'' | '"' | '\\'))
    {
        name_end += 1;
    }
    if name_end == name_start {
        return None;
    }
    position = name_end;
    if text.get(position) == Some(&'\\') {
        position += 1;
    }
    if !text
        .get(position)
        .is_some_and(|character| matches!(character, '\'' | '"'))
    {
        return None;
    }
    position = skip_space(text, position + 1);
    if text.get(position) != Some(&')') {
        return None;
    }
    Some((name_start, name_end, position + 1))
}

/// Replace every interpolation site with an identifier of the same length.
pub(crate) fn analysis_sql(text: &[char], context: &ScanContext) -> AnalysisSql {
    let mut sql = String::new();
    let mut tables: Vec<((String, String), BTreeSet<String>)> = Vec::new();
    let mut copied_to = 0;
    for (index, site) in interpolation_sites(text, context.backtick_identifiers, context.python)
        .into_iter()
        .enumerate()
    {
        let call = resource_call(&chars(&site.text));
        let kind: char = call
            .as_ref()
            .and_then(|(kind, ..)| kind.chars().next())
            .unwrap_or(GENERIC_PLACEHOLDER_KIND);
        let placeholder = placeholder(kind, index, site.end - site.start);
        if let Some((kind, name, ..)) = call {
            let key = (kind, name);
            match tables.iter_mut().find(|(item, _)| *item == key) {
                Some((_, placeholders)) => {
                    placeholders.insert(placeholder.clone());
                }
                None => tables.push((key, BTreeSet::from([placeholder.clone()]))),
            }
        }
        sql.push_str(&slice(text, copied_to, site.start));
        sql.push_str(&placeholder);
        copied_to = site.end;
    }
    sql.push_str(&slice(text, copied_to, text.len()));
    AnalysisSql { sql, tables }
}

fn placeholder(kind: char, index: usize, length: usize) -> String {
    let base = format!("_q{kind}{index}");
    let base_length = base.chars().count();
    if base_length > length {
        let mut padded: String =
            std::iter::repeat_n(PLACEHOLDER_PAD, length.saturating_sub(1)).collect();
        padded.push(kind);
        return padded;
    }
    let mut padded = base;
    padded.extend(std::iter::repeat_n(PLACEHOLDER_PAD, length - base_length));
    padded
}

/// The mappable compiled body of a model, or `None` when it cannot be mapped.
pub(crate) fn model_body(model: &ModelFacts, contents: &[char]) -> Option<ModelBody> {
    if model.authored_query_sql.is_empty() {
        return None;
    }
    let body_start = rfind(contents, &model.authored_query_sql, 0, contents.len())?;
    let passes = match &model.expansion {
        Some(expansion) => {
            if expansion.expanded_sql != model.query_sql {
                return None;
            }
            expansion.passes.clone()
        }
        None if model.query_sql != model.authored_query_sql => return None,
        None => Vec::new(),
    };
    Some(ModelBody {
        body_start,
        compiled_sql: model.query_sql.clone(),
        passes,
    })
}

/// Resolve one rendered offset through one expansion pass (`map_output_offset`).
fn map_output_offset(offset: usize, spans: &[ExpansionSpan]) -> (usize, bool) {
    let mut mapped = offset as i64;
    for span in spans {
        if offset < span.output_start {
            break;
        }
        if offset < span.output_end {
            return (span.source_start, true);
        }
        mapped += (span.source_end as i64 - span.source_start as i64)
            - (span.output_end as i64 - span.output_start as i64);
    }
    (usize::try_from(mapped).unwrap_or(0), false)
}

/// The file offset of a compiled offset and whether a macro generated it.
pub(crate) fn authored_offset(body: &ModelBody, offset: usize) -> (usize, bool) {
    let mut current = offset;
    let mut generated = false;
    for spans in body.passes.iter().rev() {
        let (resolved, was_generated) = map_output_offset(current, spans);
        current = resolved;
        generated = generated || was_generated;
    }
    (body.body_start + current, generated)
}

/// The file span of compiled text written by the author, or `None` if generated.
pub(crate) fn authored_span(body: &ModelBody, start: usize, end: usize) -> Option<(usize, usize)> {
    let (mapped_start, start_generated) = authored_offset(body, start);
    if start_generated {
        return None;
    }
    if end <= start {
        return Some((mapped_start, mapped_start));
    }
    let (mapped_last, last_generated) = authored_offset(body, end - 1);
    if last_generated || mapped_last as i64 - mapped_start as i64 != (end - 1 - start) as i64 {
        return None;
    }
    Some((mapped_start, mapped_last + 1))
}
