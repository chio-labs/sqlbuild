//! Ordered mappings shared with Python's dicts.

/// An adapter's Python nullability rule: `(function name, argument nullabilities)` to a result.
pub type NullabilityRuleFn =
    dyn Fn(&str, &[&'static str]) -> Result<&'static str, String> + Send + Sync;

/// An ordered `name -> value` mapping in Python dict order.
pub type Pairs = Vec<(String, String)>;
/// Ordered relation shapes in Python dict order.
pub type Shapes = Vec<(String, Pairs)>;
/// `(output column, [(resource name, column name)])` per output, in lineage order.
pub type OutputSources = Vec<(String, Vec<(String, String)>)>;
