//! Ordered mappings shared with Python's dicts.

/// An ordered `name -> value` mapping in Python dict order.
pub type Pairs = Vec<(String, String)>;
/// Ordered relation shapes in Python dict order.
pub type Shapes = Vec<(String, Pairs)>;
