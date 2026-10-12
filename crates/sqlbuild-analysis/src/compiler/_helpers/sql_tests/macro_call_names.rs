//! Python's `find_macro_call_names` over a model's pre-macro SQL.

use sqlbuild_render::macro_calls::main::macro_call_names::macro_call_names as scanned_names;

/// Declaration calls expansion substitutes rather than running as macros.
const DECLARATION_CALLS: [&str; 2] = ["enum", "const"];

/// The names Python's scan returns, or the message of the `CompileInputError` it raises.
pub(crate) fn macro_call_names(sql: &str) -> Result<Vec<String>, String> {
    let mut names: Vec<String> =
        scanned_names(sql, false).map_err(|error| error.message().to_owned())?;
    names.retain(|name| !DECLARATION_CALLS.contains(&name.as_str()));
    Ok(names)
}
