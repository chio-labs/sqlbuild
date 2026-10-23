//! Lookup tables of Python import rewriting.

use std::collections::{BTreeMap, BTreeSet};

/// Each moved module's dotted parts, before and after.
pub(crate) type ModuleMoves = BTreeMap<Vec<String>, Vec<String>>;
/// The names each project package's `__init__.py` binds, by package parts.
pub(crate) type PackageBindings = BTreeMap<Vec<String>, BTreeSet<String>>;
