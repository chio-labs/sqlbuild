//! Python's `normalize_type(...).family` through the native type system, noting text fallbacks.

use std::cell::RefCell;

use crate::semantic_checks::constants::GENERIC_DIALECT;
use crate::semantic_checks::models::SemanticDeferral;
use crate::type_system::main::normalize_type::normalize_type;
use crate::type_system::models::{TypeFamily, TypeNormalization};

const NUMERIC_FAMILIES: [TypeFamily; 3] =
    [TypeFamily::Integer, TypeFamily::Decimal, TypeFamily::Float];
const TEMPORAL_FAMILIES: [TypeFamily; 3] = [
    TypeFamily::Timestamp,
    TypeFamily::Date,
    TypeFamily::Datetime,
];

/// Type families for one dialect, remembering types Python logs a parse fallback for.
pub(crate) struct Families {
    dialect: String,
    fallback_types: RefCell<Vec<String>>,
}

impl Families {
    pub(crate) fn new(dialect: Option<&str>) -> Self {
        Self {
            dialect: dialect.unwrap_or(GENERIC_DIALECT).to_owned(),
            fallback_types: RefCell::new(Vec::new()),
        }
    }

    /// The family of `type_sql`, or a deferral where Python would leave the native type system.
    pub(crate) fn family(&self, type_sql: &str) -> Result<TypeFamily, SemanticDeferral> {
        let normalization: TypeNormalization =
            normalize_type(type_sql, &self.dialect).ok_or(SemanticDeferral::UnsupportedType)?;
        if normalization.parse_error.is_some() {
            self.fallback_types.borrow_mut().push(type_sql.to_owned());
        }
        Ok(normalization.normalized.family)
    }

    /// Python's `_different_argument_families`.
    pub(crate) fn different(&self, left: &str, right: &str) -> Result<bool, SemanticDeferral> {
        let left: TypeFamily = self.family(left)?;
        let right: TypeFamily = self.family(right)?;
        let families: [TypeFamily; 2] = [left, right];
        Ok(left != right
            && !families.contains(&TypeFamily::Other)
            && !families
                .iter()
                .all(|family| NUMERIC_FAMILIES.contains(family))
            && !families
                .iter()
                .all(|family| TEMPORAL_FAMILIES.contains(family)))
    }

    /// Types whose normalization fell back to text, in the order they were normalized.
    pub(crate) fn fallback_types(self) -> Vec<String> {
        self.fallback_types.into_inner()
    }
}
