//! `ddl_script`: the complete ordered script an administrator runs to create a Recall store.

use crate::schema::main::ddl_statements::ddl_statements;
use crate::schema::main::render_script::render_script;
use crate::schema::models::{DdlOptions, Dialect};

/// The complete creation script of [`ddl_statements`].
#[must_use]
pub fn ddl_script(dialect: Dialect, options: &DdlOptions) -> String {
    render_script(&ddl_statements(dialect, options))
}
