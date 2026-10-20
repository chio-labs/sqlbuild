//! Python rows of macro call sites and splice spans.

use sqlbuild_analysis::semantic_validation::models::Expansion;
use sqlbuild_render::macro_calls::models::{MacroCallSite, MacroSpliceSpan};
use sqlbuild_sqltext::compiler::models::CharSpan;

positional_record! {
    into;
    /// One call site: start, arguments start, end, name, tree names if scanned and whether typed reference text appears.
    pub(crate) struct SiteRow {
        start: usize,
        args_start: usize,
        end: usize,
        name: String,
        tree_names: Option<Vec<String>>,
        typed_reference_text: bool,
    }
}
positional_record! {
    extract, into;
    /// One substitution span: source start and end, output start and end.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub(crate) struct SpanRow {
        pub(crate) source_start: usize,
        pub(crate) source_end: usize,
        pub(crate) output_start: usize,
        pub(crate) output_end: usize,
    }
}

impl From<CharSpan> for SpanRow {
    fn from(span: CharSpan) -> Self {
        Self {
            source_start: span.source_start,
            source_end: span.source_end,
            output_start: span.output_start,
            output_end: span.output_end,
        }
    }
}

impl From<SpanRow> for Expansion {
    fn from(span: SpanRow) -> Self {
        Self {
            source_start: span.source_start,
            source_end: span.source_end,
            output_start: span.output_start,
            output_end: span.output_end,
        }
    }
}

pub(crate) fn site_row(site: MacroCallSite) -> SiteRow {
    SiteRow {
        start: site.start,
        args_start: site.args_start,
        end: site.end,
        name: site.name,
        tree_names: site.tree_names,
        typed_reference_text: site.typed_reference_text,
    }
}

pub(crate) fn span_row(span: MacroSpliceSpan) -> SpanRow {
    SpanRow {
        source_start: span.source_start,
        source_end: span.source_end,
        output_start: span.output_start,
        output_end: span.output_end,
    }
}
