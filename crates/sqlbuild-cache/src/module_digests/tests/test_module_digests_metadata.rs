use sqlbuild_core::json::models::JsonValue;

use crate::module_digests::main::module_digests_metadata::module_digests_metadata;
use crate::module_digests::tests::helpers::text;
use crate::module_digests::tests::test_types::MetadataTestCase;

#[test]
fn given_module_digests_when_encoding_then_matches_python_sorted_json() {
    let test_cases = [
        MetadataTestCase {
            description: "rows sorted by path, non-ASCII escaped",
            rows: vec![
                (text("z/orders.py"), text("b")),
                (text("caf\u{e9}.py"), text("a")),
            ],
            expected_metadata: "[[\"caf\\u00e9.py\", \"a\"], [\"z/orders.py\", \"b\"]]",
        },
        MetadataTestCase {
            description: "a lone surrogate sorts by code point, before astral characters",
            rows: vec![
                (text("\u{1f600}.py"), text("a")),
                (JsonValue::Utf16(vec![0xdcff]), text("b")),
            ],
            expected_metadata: "[[\"\\udcff\", \"b\"], [\"\\ud83d\\ude00.py\", \"a\"]]",
        },
    ];

    for test_case in test_cases {
        let metadata = module_digests_metadata(test_case.rows).unwrap_or_default();

        assert_eq!(
            metadata, test_case.expected_metadata,
            "{}",
            test_case.description
        );
    }
}
