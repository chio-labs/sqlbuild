//! Python's dataclass `repr` of a resource or declaration identity, as `str()` prints it.

use crate::scope_index::_helpers::identities::qualified_repr;
use crate::scope_index::models::QualifiedIdentity;

/// `ResourceIdentity(kind=<ResourceKind.MODEL: 'model'>, name='orders')` and its declaration form.
#[must_use]
pub fn identity_repr(identity: &QualifiedIdentity) -> String {
    qualified_repr(identity)
}
