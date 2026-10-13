//! The namespace a loader collision reports: the first shared one by its Python `repr`.

use sqlbuild_core::text::main::python_str_repr::python_str_repr;

/// Python's `repr` of an optional string.
fn optional_repr(value: Option<&String>) -> String {
    value.map_or_else(|| "None".to_owned(), |text| python_str_repr(text))
}

/// `sorted(namespaces, key=repr)[0]` of `(database, schema)` pairs, or `None` when empty.
pub fn first_shared_namespace(
    namespaces: &[(Option<String>, Option<String>)],
) -> Option<(Option<String>, Option<String>)> {
    namespaces
        .iter()
        .min_by_key(|(database, schema)| {
            format!(
                "({}, {})",
                optional_repr(database.as_ref()),
                optional_repr(schema.as_ref())
            )
        })
        .cloned()
}
