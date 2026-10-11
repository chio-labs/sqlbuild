//! Python rows of macro call sites and splice spans.

use sqlbuild_render::macro_calls::models::{MacroCallSite, MacroSpliceSpan};

/// One call site: start, arguments start, end, name, tree names if scanned and whether typed reference text appears.
pub(crate) type SiteRow = (usize, usize, usize, String, Option<Vec<String>>, bool);
/// One substitution span: source start and end, output start and end.
pub(crate) type SpanRow = (usize, usize, usize, usize);

pub(crate) fn site_row(site: MacroCallSite) -> SiteRow {
    (
        site.start,
        site.args_start,
        site.end,
        site.name,
        site.tree_names,
        site.typed_reference_text,
    )
}

pub(crate) fn span_row(span: MacroSpliceSpan) -> SpanRow {
    (
        span.source_start,
        span.source_end,
        span.output_start,
        span.output_end,
    )
}
