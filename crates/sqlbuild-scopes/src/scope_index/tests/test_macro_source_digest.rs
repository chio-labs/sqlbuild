use crate::scope_index::main::macro_source_digest::macro_source_digest;
use crate::scope_index::tests::test_types::MacroDigestTestCase;

#[test]
fn given_macro_source_when_digesting_then_python_sha256_hex_matches() {
    let test_cases = [
        MacroDigestTestCase {
            description: "empty source",
            source: "",
            expected_digest: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        },
        MacroDigestTestCase {
            description: "a one-function macro module",
            source: "def cents(value: str) -> str:\n    return f\"{value} * 100\"\n",
            expected_digest: "a1b0650d0b624a37526376fb5059b1d9b5c790c4d27b9ee561f4f6a318f0db9e",
        },
        MacroDigestTestCase {
            description: "non-ASCII text digests its UTF-8 bytes",
            source: "caf\u{e9}",
            expected_digest: "850f7dc43910ff890f8879c0ed26fe697c93a067ad93a7d50f466a7028a9bf4e",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            macro_source_digest(test_case.source),
            test_case.expected_digest,
            "{}",
            test_case.description
        );
    }
}
