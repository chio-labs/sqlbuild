use crate::text::main::decode_python_text::decode_python_text;
use crate::text::models::LineIndex;
use crate::text::tests::test_types::{DecodeTestCase, PositionTestCase, SpanTestCase};

#[test]
fn given_offsets_when_indexing_text_then_lines_and_columns_match_python() {
    let test_cases = [
        PositionTestCase {
            description: "start of text",
            text: "select 1",
            byte_offset: 0,
            expected_position: Some((0, 1, 1)),
        },
        PositionTestCase {
            description: "end of text is addressable",
            text: "select 1",
            byte_offset: 8,
            expected_position: Some((8, 1, 9)),
        },
        PositionTestCase {
            description: "multi-byte characters count once",
            text: "-- café ☕ 😀\nselect é",
            byte_offset: 25,
            expected_position: Some((19, 2, 8)),
        },
        PositionTestCase {
            description: "tab counts as one column",
            text: "\tselect\t1",
            byte_offset: 8,
            expected_position: Some((8, 1, 9)),
        },
        PositionTestCase {
            description: "newline belongs to the line it ends",
            text: "a\nb",
            byte_offset: 1,
            expected_position: Some((1, 1, 2)),
        },
        PositionTestCase {
            description: "carriage return is an ordinary column",
            text: "a\r\nb",
            byte_offset: 3,
            expected_position: Some((3, 2, 1)),
        },
        PositionTestCase {
            description: "offset inside a character is rejected",
            text: "é",
            byte_offset: 1,
            expected_position: None,
        },
        PositionTestCase {
            description: "offset past the end is rejected",
            text: "a",
            byte_offset: 2,
            expected_position: None,
        },
    ];
    for test_case in test_cases {
        let index = LineIndex::new(test_case.text);
        let position = index.position_at_byte(test_case.byte_offset);
        let round_trip = position.and_then(|found| index.position_at_char(found.char_offset));
        assert_eq!(
            position.map(|found| (found.char_offset, found.line, found.column)),
            test_case.expected_position,
            "{}",
            test_case.description
        );
        assert_eq!(round_trip, position, "{} round trip", test_case.description);
    }
}

#[test]
fn given_byte_ranges_when_building_spans_then_both_ends_are_positions() {
    let test_cases = [
        SpanTestCase {
            description: "range on the second line",
            text: "one\ntwo é three",
            byte_range: (8, 10),
            expected_ends: Some(((2, 5), (2, 6))),
        },
        SpanTestCase {
            description: "reversed range is rejected",
            text: "one",
            byte_range: (2, 1),
            expected_ends: None,
        },
    ];
    for test_case in test_cases {
        let span = LineIndex::new(test_case.text)
            .span_at_bytes(test_case.byte_range.0, test_case.byte_range.1);
        assert_eq!(
            span.map(|found| (
                (found.start.line, found.start.column),
                (found.end.line, found.end.column)
            )),
            test_case.expected_ends,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_authored_bytes_when_decoding_then_text_matches_python_read_text() {
    let test_cases = [
        DecodeTestCase {
            description: "CRLF and lone CR become LF",
            bytes: b"a\r\nb\rc\n\r\n",
            expected_text: Ok("a\nb\nc\n\n"),
        },
        DecodeTestCase {
            description: "byte-order mark is kept",
            bytes: b"\xef\xbb\xbfselect",
            expected_text: Ok("\u{feff}select"),
        },
        DecodeTestCase {
            description: "encoded surrogate is invalid",
            bytes: b"ok\xed\xa0\x80",
            expected_text: Err(2),
        },
        DecodeTestCase {
            description: "truncated sequence is invalid",
            bytes: b"caf\xc3",
            expected_text: Err(3),
        },
    ];
    for test_case in test_cases {
        let actual = decode_python_text(test_case.bytes).map_err(|error| error.valid_up_to);
        assert_eq!(
            actual.as_deref().map_err(|offset| *offset),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}
