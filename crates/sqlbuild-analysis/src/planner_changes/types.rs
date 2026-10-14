//! Planner change-detection callback types.

use std::collections::BTreeSet;

use crate::planner_changes::models::NameSpan;

/// Finds the `__ref` spans of some names.
pub type SpanFinder<'a, E> = dyn FnMut(&BTreeSet<String>) -> Result<Vec<NameSpan>, E> + 'a;

/// Whether two type strings are equal (warehouse or family type first, expected type second).
pub type TypesEqual<'a, E> = dyn FnMut(&str, &str) -> Result<bool, E> + 'a;

/// The type of the one dynamic family accepting a column name, if exactly one does.
pub type SingleFamilyType<'a, E> = dyn FnMut(&str) -> Result<Option<String>, E> + 'a;

/// Hashes a candidate query.
pub type QueryHasher<'a, E> = dyn FnMut(&str) -> Result<String, E> + 'a;

/// The column checks schema comparison asks the caller: type equality and single-family type.
pub type SchemaChecks<'a, E> = (&'a mut TypesEqual<'a, E>, &'a mut SingleFamilyType<'a, E>);

/// How rename matching finds `__ref` spans and hashes a candidate query.
pub type RenameMatching<'a, E> = (&'a mut SpanFinder<'a, E>, &'a mut QueryHasher<'a, E>);
