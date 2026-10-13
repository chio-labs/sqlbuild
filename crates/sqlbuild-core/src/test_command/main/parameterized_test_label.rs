//! The label of a test row.

use crate::test_command::models::TestParameter;

/// The name, with source path and typed values only for parameterized cases.
#[must_use]
pub fn parameterized_test_label(
    name: &str,
    source_path: Option<&str>,
    parameters: &[TestParameter],
) -> String {
    let Some(source_path) = source_path else {
        return name.to_owned();
    };
    if parameters.is_empty() {
        return name.to_owned();
    }
    let rendered: Vec<String> = parameters
        .iter()
        .map(|parameter| {
            format!(
                "{}:{}{}={}",
                parameter.name,
                parameter.value_type,
                if parameter.nullable { "?" } else { "" },
                parameter.rendered
            )
        })
        .collect();
    format!("{name} ({source_path}; {})", rendered.join(", "))
}
