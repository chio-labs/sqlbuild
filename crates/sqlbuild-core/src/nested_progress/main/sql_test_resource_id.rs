//! The execution-protocol identity of one SQL test case.

/// `sql_test:<name>`, or `sql_test:<path>:<block>:<case>` for one parameterised case.
#[must_use]
pub fn sql_test_resource_id(test_name: &str, case: Option<(&str, i64, &str)>) -> String {
    match case {
        Some((source_path, block_index, case_name)) => {
            format!("sql_test:{source_path}:{block_index}:{case_name}")
        }
        None => format!("sql_test:{test_name}"),
    }
}
