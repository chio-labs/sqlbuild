//! The identity keys compile usages are merged by.

/// A declaration's kind, name and private owner `(kind, name)`; a resource's kind and name with no owner.
pub type QualifiedKey = (String, String, Option<(String, String)>);
