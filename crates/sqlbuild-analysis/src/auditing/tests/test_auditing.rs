use std::convert::Infallible;

use crate::auditing::main::audit_gate_identity::audit_gate_identity;
use crate::auditing::main::evaluate_measurement::evaluate_measurement;
use crate::auditing::main::replace_reference_calls::replace_reference_calls;
use crate::auditing::models::{MeasurementOutcome, ThresholdBound, Thresholds};
use crate::auditing::tests::helpers::{planned, ratio_measurement};
use crate::auditing::tests::test_types::{
    GateIdentityTestCase, MeasurementTestCase, ReplaceTestCase,
};

#[test]
fn given_planned_audits_when_hashing_gate_then_matches_python_identity() {
    let test_cases = [GateIdentityTestCase {
        description: "a violation and a measurement audit with non-ASCII names and float repr",
        measurement_name: "ratio_\u{e9}",
        expected_binding_set_hash: "ae6bb2e0d7f4a3cd00d11b9cf656701fd3c18f6b7ed548199857a4027ea3038b",
        expected_blocking_set_hash: "8d05e01eb554dc405c2775f729ddfadd885b43178a3e7e3e437b98cc1d3783df",
        expected_order: [1, 0],
    }];

    for test_case in test_cases {
        let audits = [
            planned("not_null", "error", None),
            planned(
                test_case.measurement_name,
                "warn",
                Some(ratio_measurement()),
            ),
        ];
        let gate = audit_gate_identity(&audits);
        let order: Vec<usize> = gate.audits.iter().map(|audit| audit.index).collect();
        assert_eq!(
            (
                gate.binding_set_hash.as_str(),
                gate.blocking_set_hash.as_str(),
                order
            ),
            (
                test_case.expected_binding_set_hash,
                test_case.expected_blocking_set_hash,
                test_case.expected_order.to_vec()
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_measurements_when_evaluating_then_returns_python_outcomes() {
    let below = Thresholds {
        warn: Some(ThresholdBound::Below(10.0)),
        error: Some(ThresholdBound::Below(5.0)),
    };
    let test_cases = [
        MeasurementTestCase {
            description: "an error bound wins over a warn bound",
            measured: 4.0,
            samples: (None, None),
            thresholds: below,
            expected_outcome: Ok(MeasurementOutcome::Error),
        },
        MeasurementTestCase {
            description: "only the warn bound is violated",
            measured: 7.0,
            samples: (Some(3), Some(3)),
            thresholds: below,
            expected_outcome: Ok(MeasurementOutcome::Warn),
        },
        MeasurementTestCase {
            description: "too few samples are insufficient",
            measured: 1.0,
            samples: (Some(2), Some(3)),
            thresholds: below,
            expected_outcome: Ok(MeasurementOutcome::Insufficient),
        },
        MeasurementTestCase {
            description: "a missing sample count is insufficient",
            measured: 1.0,
            samples: (None, Some(0)),
            thresholds: below,
            expected_outcome: Ok(MeasurementOutcome::Insufficient),
        },
        MeasurementTestCase {
            description: "a value inside an outside range passes",
            measured: 0.5,
            samples: (None, None),
            thresholds: Thresholds {
                warn: Some(ThresholdBound::Outside(0.0, 1.0)),
                error: None,
            },
            expected_outcome: Ok(MeasurementOutcome::Pass),
        },
        MeasurementTestCase {
            description: "a non-finite value is rejected",
            measured: f64::NAN,
            samples: (None, None),
            thresholds: below,
            expected_outcome: Err("measured_value must be finite"),
        },
    ];

    for test_case in test_cases {
        let outcome =
            evaluate_measurement(test_case.measured, test_case.samples, test_case.thresholds);
        assert_eq!(
            outcome, test_case.expected_outcome,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_reference_calls_when_replacing_then_matches_python_regex_substitution() {
    let test_cases = [
        ReplaceTestCase {
            description: "known names are replaced and unknown calls kept",
            sql: "SELECT * FROM __ref(\"orders\") JOIN __ref(\"missing\") USING (id)",
            expected_sql: "SELECT * FROM main.orders JOIN __ref(\"missing\") USING (id)",
        },
        ReplaceTestCase {
            description: "an empty or unclosed call is skipped and a later call still matches",
            sql: "__ref(\"\") __ref(\"a\" ) __ref(\"orders\")",
            expected_sql: "__ref(\"\") __ref(\"a\" ) main.orders",
        },
        ReplaceTestCase {
            description: "an unclosed name does not hide a later call",
            sql: "__ref(\"x) __ref(\"orders\")",
            expected_sql: "__ref(\"x) main.orders",
        },
    ];

    for test_case in test_cases {
        let replaced = replace_reference_calls(test_case.sql, "__ref", |name| {
            Ok::<Option<String>, Infallible>((name == "orders").then(|| "main.orders".to_owned()))
        });
        assert_eq!(
            replaced,
            Ok(test_case.expected_sql.to_owned()),
            "{}",
            test_case.description
        );
    }
}
