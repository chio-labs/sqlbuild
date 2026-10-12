//! Static reading of project Python source; CPython stays the authority on syntax validity.

#![forbid(unsafe_code)]

pub(crate) mod cpython_tree;
pub mod literal_sql;
pub mod macro_modules;
pub mod module_parse;
