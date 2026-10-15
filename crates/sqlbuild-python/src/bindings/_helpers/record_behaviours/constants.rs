//! Native behaviour of the hosted shapes: computed attributes, methods, ordering and validation.

use crate::bindings::_helpers::record_behaviours::scopes::{
    completeness_complete, target_query_unknown,
};
use crate::bindings::_helpers::records::types::{ClassMethod, ClassProperty, RecordFinish};

/// Compiler records whose bound values are normalized or validated natively.
pub(crate) const BEHAVIOUR_FINISHERS: &[(&str, RecordFinish)] = &[];
/// Computed attributes of compiler shapes.
pub(crate) const BEHAVIOUR_PROPERTIES: &[(&str, &str, ClassProperty)] = &[
    ("ScopeCompleteness", "complete", completeness_complete),
    ("ScopeTargetQuery", "unknown", target_query_unknown),
];
/// Methods of compiler shapes.
pub(crate) const BEHAVIOUR_METHODS: &[(&str, &str, ClassMethod)] = &[];
/// Compiler records ordered by their compared fields.
pub(crate) const BEHAVIOUR_ORDERED: &[&str] =
    &["ResourceIdentity", "DeclarationIdentity", "OwnershipRoot"];
