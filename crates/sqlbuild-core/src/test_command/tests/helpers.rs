use crate::test_command::models::TestParameter;

/// A string parameter with its rendered JSON value.
pub(super) fn parameter(name: &str, nullable: bool, rendered: &str) -> TestParameter {
    TestParameter {
        name: name.to_owned(),
        value_type: "string".to_owned(),
        nullable,
        rendered: rendered.to_owned(),
    }
}
