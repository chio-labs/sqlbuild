use crate::algebra::errors::CursorError;
use crate::algebra::main::floor_to_grain::floor_to_grain;
use crate::algebra::main::next_boundary::next_boundary;
use crate::algebra::main::normalize_timestamp_text::normalize_timestamp_text;
use crate::algebra::main::render::render;
use crate::algebra::models::{Grain, ZoneOffset};
use crate::algebra::tests::helpers::{civil, date, integer, local, naive, timestamp};
use crate::algebra::tests::test_types::{NoZones, RenderTestCase, StepTestCase, TextTestCase};

const INDIA_OFFSET: i64 = 19_800_000_000;

#[test]
fn given_cursor_value_when_flooring_and_stepping_then_matches_python_datetime() {
    let test_cases = [
        StepTestCase {
            description: "leap-day timestamp floored to the month steps to March",
            value: timestamp(
                local(civil(2024, 2, 29), (13, 45, 12, 345_678)),
                ZoneOffset::Naive,
            ),
            grain: Grain::Month,
            expected_floor: naive(2024, 2, 1, 0),
            expected_next: Ok(naive(2024, 3, 1, 0)),
        },
        StepTestCase {
            description: "hour grain keeps a fixed offset and steps one hour",
            value: timestamp(
                local(civil(2024, 12, 31), (23, 30, 0, 0)),
                ZoneOffset::Fixed(INDIA_OFFSET),
            ),
            grain: Grain::Hour,
            expected_floor: timestamp(
                local(civil(2024, 12, 31), (23, 0, 0, 0)),
                ZoneOffset::Fixed(INDIA_OFFSET),
            ),
            expected_next: Ok(timestamp(
                local(civil(2025, 1, 1), (0, 0, 0, 0)),
                ZoneOffset::Fixed(INDIA_OFFSET),
            )),
        },
        StepTestCase {
            description: "a day-grained date is already aligned and steps a day",
            value: date(2023, 2, 28),
            grain: Grain::Day,
            expected_floor: date(2023, 2, 28),
            expected_next: Ok(date(2023, 3, 1)),
        },
        StepTestCase {
            description: "the last year fails as date.replace does",
            value: date(9999, 7, 4),
            grain: Grain::Year,
            expected_floor: date(9999, 1, 1),
            expected_next: Err(CursorError::Value("year 10000 is out of range".to_owned())),
        },
        StepTestCase {
            description: "the last second fails as datetime addition does",
            value: timestamp(
                local(civil(9999, 12, 31), (23, 59, 59, 1)),
                ZoneOffset::Naive,
            ),
            grain: Grain::Second,
            expected_floor: timestamp(
                local(civil(9999, 12, 31), (23, 59, 59, 0)),
                ZoneOffset::Naive,
            ),
            expected_next: Err(CursorError::Overflow("date value out of range".to_owned())),
        },
        StepTestCase {
            description: "integers are their own partitions",
            value: integer(41),
            grain: Grain::Day,
            expected_floor: integer(41),
            expected_next: Ok(integer(42)),
        },
    ];

    for test_case in test_cases {
        let floored = floor_to_grain(&test_case.value, Some(test_case.grain));
        let next = next_boundary(&floored, Some(test_case.grain));

        assert_eq!(
            floored, test_case.expected_floor,
            "{}",
            test_case.description
        );
        assert_eq!(next, test_case.expected_next, "{}", test_case.description);
    }
}

#[test]
fn given_timestamp_text_when_normalizing_then_joins_the_zone_suffix() {
    let test_cases = [
        TextTestCase {
            description: "space before an offset with a separator",
            text: " 2024-01-01 00:00:00 +05:30 ",
            expected_text: "2024-01-01 00:00:00+05:30",
        },
        TextTestCase {
            description: "Unicode spaces and digits before a compact offset",
            text: "2024-01-01 00:00:00\u{3000}-\u{0660}800",
            expected_text: "2024-01-01 00:00:00-\u{0660}800",
        },
        TextTestCase {
            description: "a UTC designator",
            text: "2024-01-01T10:00:00 \tZ",
            expected_text: "2024-01-01T10:00:00Z",
        },
        TextTestCase {
            description: "an hour-only offset is left alone",
            text: "2024-01-01 00:00:00 +05",
            expected_text: "2024-01-01 00:00:00 +05",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            normalize_timestamp_text(test_case.text),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_cursor_value_when_rendering_then_matches_isoformat() {
    let test_cases = [
        RenderTestCase {
            description: "an early year with microseconds and a second-level offset",
            value: timestamp(
                local(civil(5, 1, 1), (0, 0, 0, 7)),
                ZoneOffset::Fixed(-10_807_000_003),
            ),
            expected_text: Ok("0005-01-01T00:00:00.000007-03:00:07.000003".to_owned()),
        },
        RenderTestCase {
            description: "a date",
            value: date(2024, 2, 29),
            expected_text: Ok("2024-02-29".to_owned()),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            render(&test_case.value, &NoZones),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}
