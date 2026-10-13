use crate::freshness::errors::FreshnessError;
use crate::freshness::main::records_equivalent::records_equivalent;
use crate::freshness::tests::helpers::record;
use crate::freshness::tests::test_types::{EquivalenceTestCase, MinuteParser};

#[test]
fn given_timestamp_records_when_comparing_then_lag_tolerance_decides() {
    let test_cases = [
        EquivalenceTestCase {
            description: "later within a two-hour tolerance across a month end",
            previous: "2024-01-31T23:30",
            current: "2024-02-01T01:30",
            lag_tolerance: Some("2h"),
            expected_equivalent: Ok(true),
        },
        EquivalenceTestCase {
            description: "later beyond a fifteen-minute tolerance",
            previous: "2024-01-31T23:30",
            current: "2024-01-31T23:46",
            lag_tolerance: Some("15m"),
            expected_equivalent: Ok(false),
        },
        EquivalenceTestCase {
            description: "an earlier value is never equivalent",
            previous: "2024-01-31T23:30",
            current: "2024-01-31T23:29",
            lag_tolerance: Some("1d"),
            expected_equivalent: Ok(false),
        },
        EquivalenceTestCase {
            description: "a calendar tolerance is rejected",
            previous: "2024-01-31T23:30",
            current: "2024-01-31T23:31",
            lag_tolerance: Some("1mo"),
            expected_equivalent: Err(FreshnessError::Observation(
                "source freshness lag_tolerance must be a positive duration like 15m, 2h, or 1d"
                    .to_owned(),
            )),
        },
    ];

    for test_case in test_cases {
        let (previous, current) = (record(test_case.previous), record(test_case.current));

        assert_eq!(
            records_equivalent(
                (&previous, &current),
                test_case.lag_tolerance,
                &MinuteParser
            ),
            test_case.expected_equivalent,
            "{}",
            test_case.description
        );
    }
}
