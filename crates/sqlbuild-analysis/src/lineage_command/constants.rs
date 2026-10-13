//! Directions, formats and labels of `sqb lineage`.

pub const UPSTREAM_DIRECTION: &str = "upstream";
pub const DOWNSTREAM_DIRECTION: &str = "downstream";
pub const BOTH_DIRECTIONS: &str = "both";
pub const JSON_OUTPUT_FORMAT: &str = "json";
pub const LIST_OUTPUT_FORMAT: &str = "list";
pub const UNLIMITED_DEPTH_VALUE: &str = "all";
pub const COLUMN_TARGET_SEPARATOR: char = '.';
pub const COLUMN_TARGET_KIND: &str = "column";
pub const MODEL_RESOURCE_TYPE: &str = "model";
pub const SELECTOR_INTERSECTION_MARKER: char = ',';
/// Column-lineage model count from which rich analysis shows a status spinner.
pub const RICH_STATUS_MODEL_THRESHOLD: usize = 100;
pub(crate) const KIND_SEPARATOR: char = ':';
pub(crate) const GRAPH_OPERATORS: [char; 3] = ['+', '@', '*'];
/// Kind prefixes a lineage target may carry.
pub(crate) const TARGET_KINDS: [&str; 6] = ["model", "source", "seed", "udf", "table_fn", "column"];
pub(crate) const HUMAN_COLUMN_TRACE_LIMIT: usize = 25;
pub(crate) const STAR_TRANSFORM: &str = "star";
pub(crate) const STAR_TRANSFORM_LABEL: &str = "from SELECT *";
pub(crate) const ALREADY_SHOWN: &str = " (already shown)";
pub(crate) const DEPTH_MESSAGE: &str = "--depth must be a non-negative integer or 'all'";
