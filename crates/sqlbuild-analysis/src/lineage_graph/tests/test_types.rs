use std::collections::HashMap;

use crate::lineage_graph::models::AnalysisDialect;

/// `(resource, column)`.
pub(crate) type ColumnRef = (&'static str, &'static str);

pub(crate) struct EdgeIndexTestCase {
    pub(crate) description: &'static str,
    pub(crate) edges: &'static [(ColumnRef, ColumnRef)],
    pub(crate) expected_targeting_orders: &'static [usize],
    pub(crate) expected_sourced_from_orders: &'static [usize],
    pub(crate) expected_first_equal: &'static [usize],
}

pub(crate) struct AnalysisDialectTestCase {
    pub(crate) description: &'static str,
    pub(crate) normalized: &'static str,
    pub(crate) expected_dialect: AnalysisDialect<'static>,
}

pub(crate) struct TreeLinesTestCase {
    pub(crate) description: &'static str,
    pub(crate) children: &'static [(&'static str, &'static [&'static str])],
    pub(crate) roots: &'static [&'static str],
    pub(crate) seen: &'static [&'static str],
    pub(crate) expected_lines: &'static [&'static str],
}

/// A string tree whose lines render as `prefix + branch + node`, repeats marked `(shown)`.
pub(crate) struct StringTree {
    pub(crate) children: HashMap<&'static str, Vec<&'static str>>,
    pub(crate) lines: Vec<String>,
}
