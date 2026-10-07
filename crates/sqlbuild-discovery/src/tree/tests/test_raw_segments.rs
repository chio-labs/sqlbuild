use crate::tree::_helpers::raw_names::{display_text, escaped_wide};
use crate::tree::tests::helpers::segment_points;
use crate::tree::tests::test_types::{RawSegmentTestCase, WideUnitsTestCase};

#[test]
fn given_raw_segments_when_displaying_and_decoding_then_python_sees_its_own_string() {
    let test_cases = [
        RawSegmentTestCase {
            description: "a valid name is unchanged",
            segment: "orders.sql",
            expected_display: "orders.sql",
            expected_code_points: &[0x6F, 0x72, 0x64, 0x65, 0x72, 0x73, 0x2E, 0x73, 0x71, 0x6C],
        },
        RawSegmentTestCase {
            description: "an invalid byte is surrogate-escaped and shown lossily",
            segment: "a\u{FFFD}\u{0}61e9\u{0}",
            expected_display: "a\\xe9",
            expected_code_points: &[0x61, 0xDCE9],
        },
        RawSegmentTestCase {
            description: "a cut sequence escapes each of its bytes",
            segment: "\u{FFFD}\u{0}e282\u{0}",
            expected_display: "\\xe2\\x82",
            expected_code_points: &[0xDCE2, 0xDC82],
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            (
                display_text(test_case.segment).into_owned(),
                segment_points(test_case.segment)
            ),
            (
                test_case.expected_display.to_owned(),
                test_case.expected_code_points.to_vec()
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_windows_units_when_decoding_then_lone_surrogates_are_kept() {
    let test_cases = [WideUnitsTestCase {
        description: "a lone surrogate stays as Python's str keeps it",
        units: &[0x61, 0xD800, 0xD83D, 0xDE00],
        expected_code_points: &[0x61, 0xD800, 0x1F600],
    }];
    for test_case in test_cases {
        assert_eq!(
            escaped_wide(test_case.units),
            test_case.expected_code_points,
            "{}",
            test_case.description
        );
    }
}
