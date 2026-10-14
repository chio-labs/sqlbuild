use crate::planner_migrations::main::{compatibility_findings, match_migrations};
use crate::planner_migrations::models::{CompatibilityFinding, MigrationCandidate};
use crate::planner_migrations::tests::test_types::{CompatibilityTestCase, MigrationMatchTestCase};
use std::collections::BTreeMap;

#[test]
fn given_type_changes_when_checking_compatibility_then_history_policy_is_preserved()
-> Result<(), String> {
    let test_cases = [
        CompatibilityTestCase {
            expected_type: "INTEGER",
            actual_type: "BIGINT",
            snapshot: false,
            policy: "append_new_columns",
            description: "incremental numeric conversion",
            expected_findings: &[],
        },
        CompatibilityTestCase {
            expected_type: "INTEGER",
            actual_type: "VARCHAR",
            description: "incompatible families",
            snapshot: false,
            policy: "append_new_columns",
            expected_findings: &[
                "column amount is VARCHAR in the origin but the model produces INTEGER (incompatible types)",
            ],
        },
        CompatibilityTestCase {
            expected_type: "INTEGER",
            actual_type: "BIGINT",
            snapshot: false,
            policy: "fail",
            description: "fail policy blocks convertible changes",
            expected_findings: &[
                "column amount is BIGINT in the origin but the model produces INTEGER (on_schema_change fail)",
            ],
        },
        CompatibilityTestCase {
            expected_type: "VARCHAR(10)",
            description: "snapshot fits the existing string length",
            actual_type: "VARCHAR(20)",
            snapshot: true,
            policy: "deny",
            expected_findings: &[],
        },
        CompatibilityTestCase {
            expected_type: "VARCHAR(30)",
            description: "snapshot exceeds the existing string length",
            actual_type: "VARCHAR(20)",
            snapshot: true,
            policy: "deny",
            expected_findings: &[
                "column amount is VARCHAR(20) in the origin but the model produces VARCHAR(30) (snapshot type change)",
            ],
        },
    ];
    for test_case in test_cases {
        let findings = [CompatibilityFinding {
            kind: "column_type_changed".to_owned(),
            column_name: "amount".to_owned(),
            expected_type: Some(test_case.expected_type.to_owned()),
            actual_type: Some(test_case.actual_type.to_owned()),
        }];
        assert_eq!(
            compatibility_findings::compatibility_findings(
                &findings,
                (test_case.policy, test_case.snapshot),
                "snowflake"
            )?,
            test_case.expected_findings,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_candidate_collisions_when_matching_then_only_unique_origins_survive() -> Result<(), String>
{
    let test_cases = [
        MigrationMatchTestCase {
            hashes: &["a"],
            candidates: &[],
            description: "no origins",
            expected_matches: &[],
            expected_ambiguous: 0,
        },
        MigrationMatchTestCase {
            hashes: &["a", "b"],
            description: "two unique origins",
            candidates: &[("old_orders", "a"), ("old_customers", "b")],
            expected_matches: &[(0, 0), (1, 1)],
            expected_ambiguous: 0,
        },
        MigrationMatchTestCase {
            hashes: &["a", "a"],
            description: "contested origin rejected for both models",
            candidates: &[("old_orders", "a")],
            expected_matches: &[],
            expected_ambiguous: 2,
        },
        MigrationMatchTestCase {
            hashes: &["a"],
            candidates: &[("old_orders", "a"), ("old_customers", "a")],
            description: "ambiguous candidates rejected",
            expected_matches: &[],
            expected_ambiguous: 1,
        },
        MigrationMatchTestCase {
            hashes: &["a"],
            candidates: &[("old_orders", "a"), ("old_orders", "a")],
            description: "duplicate candidate names retain the last value",
            expected_matches: &[(0, 1)],
            expected_ambiguous: 0,
        },
    ];
    for test_case in test_cases {
        let names: Vec<String> = (0..test_case.hashes.len())
            .map(|index| index.to_string())
            .collect();
        let candidates: Vec<MigrationCandidate> = test_case
            .candidates
            .iter()
            .map(|(name, fingerprint)| MigrationCandidate {
                name: (*name).to_owned(),
                fingerprint: (*fingerprint).to_owned(),
            })
            .collect();
        let result = match_migrations::match_migrations(
            &names,
            &[BTreeMap::new()],
            &candidates,
            |name, _| {
                let index = name.parse::<usize>().map_err(|error| error.to_string())?;
                Ok::<_, String>(vec![test_case.hashes[index].to_owned()])
            },
        )?;
        let expected_matches: Vec<(String, usize)> = test_case
            .expected_matches
            .iter()
            .map(|(model, candidate)| (model.to_string(), *candidate))
            .collect();
        assert_eq!(
            result.matches, expected_matches,
            "{}",
            test_case.description
        );
        assert_eq!(
            result.ambiguous.len(),
            test_case.expected_ambiguous,
            "{}",
            test_case.description
        );
    }
    Ok(())
}
