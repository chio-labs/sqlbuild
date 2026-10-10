//! Ordered mappings shared with Python's dicts.

use std::fmt;
use std::sync::Arc;

/// An adapter's own Python nullability rule: `(declared function name, argument nullabilities)`
/// to the rule's nullability, or the failure the rule raised.
pub type NullabilityRuleFn =
    dyn Fn(&str, &[&'static str]) -> Result<&'static str, String> + Send + Sync;

/// The callback that runs project-local adapter nullability rules, the `python` rule id.
#[derive(Clone)]
pub struct NullabilityCallback(pub Arc<NullabilityRuleFn>);

impl fmt::Debug for NullabilityCallback {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("NullabilityCallback")
    }
}

/// An ordered `name -> value` mapping in Python dict order.
pub type Pairs = Vec<(String, String)>;
/// Ordered relation shapes in Python dict order.
pub type Shapes = Vec<(String, Pairs)>;
/// `(output column, [(resource name, column name)])` per output, in lineage order.
pub type OutputSources = Vec<(String, Vec<(String, String)>)>;
