//! Python's `types_equal` over the native type system.

use std::cell::RefCell;
use std::collections::HashMap;

use crate::type_system::main::normalize_type::normalize_type;
use crate::type_system::models::{NormalizedType, TypeNormalization, TypeNormalizationError};

/// Whether two type strings normalize to the same comparison shape.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum TypeComparison {
    Equal,
    Different,
}

/// One request's type comparisons, normalizing each type string once as Python's cache does.
pub(crate) struct TypeComparer<'a> {
    dialect: &'a str,
    normalized: RefCell<HashMap<String, Result<NormalizedType, TypeNormalizationError>>>,
}

impl<'a> TypeComparer<'a> {
    pub(crate) fn new(dialect: &'a str) -> Self {
        Self {
            dialect,
            normalized: RefCell::new(HashMap::new()),
        }
    }

    /// Compare two types as Python's `types_equal`, or Python's normalization error.
    pub(crate) fn types_equal(
        &self,
        left: &str,
        right: &str,
    ) -> Result<TypeComparison, TypeNormalizationError> {
        let left: NormalizedType = self.normalized(left)?;
        let right: NormalizedType = self.normalized(right)?;
        Ok(if left == right {
            TypeComparison::Equal
        } else {
            TypeComparison::Different
        })
    }

    fn normalized(&self, type_sql: &str) -> Result<NormalizedType, TypeNormalizationError> {
        if let Some(known) = self.normalized.borrow().get(type_sql) {
            return known.clone();
        }
        let normalized: Result<NormalizedType, TypeNormalizationError> =
            normalize_type(type_sql, self.dialect)
                .map(|TypeNormalization { normalized, .. }| normalized);
        self.normalized
            .borrow_mut()
            .insert(type_sql.to_owned(), normalized.clone());
        normalized
    }
}
