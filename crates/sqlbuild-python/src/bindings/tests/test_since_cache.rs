use std::path::{Path, PathBuf};

use crate::bindings::_helpers::change_selection::base_cache::cache_key_with;
use crate::bindings::tests::test_types::CacheKeyTestCase;

const BASE_ENVIRONMENT: [(&str, &str); 2] = [("ORDERS_REGION", "eu"), ("UNREAD_SETTING", "a")];

fn project_reading_environment() -> PathBuf {
    let root: PathBuf = std::env::temp_dir()
        .join(format!("sqlbuild-since-cache-{}", std::process::id()))
        .join("project");
    let _ = std::fs::create_dir_all(root.join("models"));
    let _ = std::fs::write(
        root.join("models/orders.sql"),
        "SELECT order_id FROM orders WHERE region = '@@ENV:ORDERS_REGION'\n",
    );
    root
}

fn key(project: &Path, values: &[(&str, &str)]) -> String {
    let lookup = |name: &str| -> Option<String> {
        values
            .iter()
            .find(|(candidate, _)| *candidate == name)
            .map(|(_, value)| (*value).to_owned())
    };
    cache_key_with(project, (None, "{}", ""), &lookup).expect("the project reads")
}

#[test]
fn given_referenced_environment_variable_when_keying_base_cache_then_its_value_counts() {
    let project: PathBuf = project_reading_environment();
    let base_key: String = key(&project, &BASE_ENVIRONMENT);
    let test_cases = [
        CacheKeyTestCase {
            description: "a referenced variable with a new value changes the key",
            changed: &[("ORDERS_REGION", "us"), ("UNREAD_SETTING", "a")],
            expected_same_key: false,
        },
        CacheKeyTestCase {
            description: "an unset referenced variable changes the key",
            changed: &[("UNREAD_SETTING", "a")],
            expected_same_key: false,
        },
        CacheKeyTestCase {
            description: "a variable the project does not read leaves the key alone",
            changed: &[("ORDERS_REGION", "eu"), ("UNREAD_SETTING", "b")],
            expected_same_key: true,
        },
    ];
    for test_case in test_cases {
        let changed_key: String = key(&project, test_case.changed);

        assert_eq!(
            changed_key == base_key,
            test_case.expected_same_key,
            "{}",
            test_case.description
        );
    }
}
