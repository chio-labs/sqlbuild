//! Why a Python shape name could not be resolved to one native class.

/// More than one natively hosted class claims the same Python shape name.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AmbiguousShapeName;
