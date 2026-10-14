//! Resolution spans and rendered cursor inputs.

/// A reference marker at UTF-8 byte offsets.
#[derive(Debug)]
pub struct ReferenceSpan {
    pub start: usize,
    pub end: usize,
    pub name: String,
    pub package: Option<String>,
}

/// The adapter-rendered bounds and comparison policy of a cursor filter.
#[derive(Debug)]
pub struct CursorFilter<'a> {
    pub column: &'a str,
    pub start: &'a str,
    pub end: &'a str,
    pub lower_inclusive: bool,
    pub typed: bool,
}

/// One source projection whose identifiers and type are rendered by the adapter.
#[derive(Debug)]
pub struct SourceProjection {
    pub name: String,
    pub cast: Option<(String, String)>,
}

/// A source cast plan in stable declaration or warehouse order.
#[derive(Debug)]
pub struct SourceCastPlan {
    pub projections: Vec<SourceProjection>,
    pub all_columns_cast: bool,
}
