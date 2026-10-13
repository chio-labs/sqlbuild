use crate::stage_capture::main::mask_capture_noise::mask_capture_noise;
use crate::stage_capture::main::shared_node_digest::shared_node_digest;
use crate::stage_capture::tests::test_types::MaskTestCase;

#[test]
fn given_capture_text_when_masking_noise_then_matches_python_patterns() {
    let test_cases = [
        MaskTestCase {
            description: "an invocation id between words is masked",
            text: "run 20261012T223835Z_81de82a3e779 done",
            expected_masked: "run <invocation-id> done",
        },
        MaskTestCase {
            description: "an invocation id inside a word is kept",
            text: "x20261012T223835Z_81de82a3e779",
            expected_masked: "x20261012T223835Z_81de82a3e779",
        },
        MaskTestCase {
            description: "an invocation id followed by a word character is kept",
            text: "20261012T223835Z_81de82a3e7790",
            expected_masked: "20261012T223835Z_81de82a3e7790",
        },
        MaskTestCase {
            description: "decimal digits of any script form an invocation id",
            text: "\u{663}\u{661}\u{662}\u{663}\u{661}\u{662}\u{663}\u{661}T123456Z_abcdefabcdef!",
            expected_masked: "<invocation-id>!",
        },
        MaskTestCase {
            description: "native store suffixes are removed only before a word boundary",
            text: "target/cache/compiler-native-v1/x and -native-v12a and -native-v3",
            expected_masked: "target/cache/compiler/x and -native-v12a and ",
        },
        MaskTestCase {
            description: "a suffix without a version is kept",
            text: "-native-v",
            expected_masked: "-native-v",
        },
        MaskTestCase {
            description: "staging folders are masked after a word boundary",
            text: "/tmp/sqb-refactor-ab_9Z/models and xsqb-refactor-q and sqb-refactor-",
            expected_masked: "/tmp/sqb-refactor-<staging>Z/models and xsqb-refactor-q and sqb-refactor-",
        },
        MaskTestCase {
            description: "a combining mark is not a word character",
            text: "caf\u{e9}-native-v2\u{301} sqb-refactor-a\u{301}",
            expected_masked: "caf\u{e9}\u{301} sqb-refactor-<staging>\u{301}",
        },
    ];

    for test_case in test_cases {
        let masked = mask_capture_noise(test_case.text);

        assert_eq!(
            masked, test_case.expected_masked,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_shared_text_when_digesting_then_masks_noise_before_hashing() {
    let test_cases = [MaskTestCase {
        description: "the digest of Python's masked text",
        text: "{\"a\":\"20261012T223835Z_81de82a3e779\"}",
        expected_masked: "ec2780ba023eb7dd5d4579e606aee7fb714e8c5373d30f2d5f3a4cdf613f6d7f",
    }];

    for test_case in test_cases {
        let digest = shared_node_digest(test_case.text);

        assert_eq!(
            digest, test_case.expected_masked,
            "{}",
            test_case.description
        );
    }
}
